import pytest
import database


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Give each test its own temporary database."""

    test_db = tmp_path / "devices.db"
    monkeypatch.setattr(database, "DB_PATH", test_db)

    database.initialize_database()

    return database


def test_device_registration(db):
    db.register_device(
        hardware_id="AA:BB:CC:DD:EE:FF",
        device_id="test-sensor-01",
        device_type="air-quality-monitor",
        location="office"
    )

    device = db.get_device("AA:BB:CC:DD:EE:FF")

    assert device is not None
    assert device["device_id"] == "test-sensor-01"
    assert device["device_type"] == "air-quality-monitor"
    assert device["location"] == "office"


def test_configuration_save_and_retrieve(db):
    hardware_id = "AA:BB:CC:DD:EE:FF"

    db.register_device(hardware_id=hardware_id)

    config = {
        "interval": 60,
        "sensors": {
            "scd40": True,
            "ens160": True
        }
    }

    version = db.save_configuration(hardware_id, config)
    result = db.get_configuration(hardware_id)

    assert version == 1
    assert result["version"] == 1
    assert result["config"] == config


def test_configuration_versioning(db):
    hardware_id = "AA:BB:CC:DD:EE:FF"

    db.register_device(hardware_id=hardware_id)

    version1 = db.save_configuration(
        hardware_id, {"interval": 60}
    )

    version2 = db.save_configuration(
        hardware_id, {"interval": 120}
    )

    result = db.get_configuration(hardware_id)

    assert version1 == 1
    assert version2 == 2
    assert result["version"] == 2
    assert result["config"]["interval"] == 120


def test_device_discovery(db):
    hardware_id = "11:22:33:44:55:66"

    device = db.discover_device(
        hardware_id,
        firmware_version="1.0.0"
    )

    assert device["hardware_id"] == hardware_id
    assert device["firmware_version"] == "1.0.0"
    assert device["last_seen"] is not None
    assert device["device_id"] is None


def test_discovery_preserves_device_information(db):
    hardware_id = "AA:BB:CC:DD:EE:FF"

    db.register_device(
        hardware_id=hardware_id,
        device_id="office-sensor",
        device_type="air-quality-monitor",
        location="office"
    )

    device = db.discover_device(
        hardware_id,
        firmware_version="1.0.1"
    )

    assert device["device_id"] == "office-sensor"
    assert device["device_type"] == "air-quality-monitor"
    assert device["location"] == "office"
    assert device["firmware_version"] == "1.0.1"


def test_update_device_status(db):
    hardware_id = "AA:BB:CC:DD:EE:FF"

    db.register_device(hardware_id=hardware_id)
    db.update_device_status(hardware_id, "1.2.0")

    device = db.get_device(hardware_id)

    assert device["firmware_version"] == "1.2.0"
    assert device["last_seen"] is not None


def test_save_and_get_template(db):
    config = {
        "interval": 60,
        "sensors": {
            "scd40": True,
            "ens160": True
        }
    }

    db.save_template(
        "air-quality-monitor",
        "Indoor air quality monitor",
        config
    )

    template = db.get_template("air-quality-monitor")

    assert template is not None
    assert template["name"] == "air-quality-monitor"
    assert template["description"] == "Indoor air quality monitor"
    assert template["config"] == config


def test_get_missing_template(db):
    assert db.get_template("does-not-exist") is None


def test_update_template(db):
    db.save_template(
        "temperature-monitor",
        "Temperature monitor",
        {"interval": 60}
    )

    db.save_template(
        "temperature-monitor",
        "Updated temperature monitor",
        {"interval": 120}
    )

    template = db.get_template("temperature-monitor")

    assert template["description"] == "Updated temperature monitor"
    assert template["config"]["interval"] == 120


def test_assign_template(db):
    hardware_id = "AA:BB:CC:DD:EE:FF"

    db.register_device(hardware_id=hardware_id)

    config = {
        "interval": 60,
        "sensors": {
            "scd40": True,
            "ens160": True
        }
    }

    db.save_template(
        "air-quality-monitor",
        "Indoor air quality monitor",
        config
    )

    result = db.assign_template(
        hardware_id,
        "air-quality-monitor"
    )

    assert result is 1

    device = db.get_device(hardware_id)
    assert device["template_name"] == "air-quality-monitor"

    # Assignment should not create a configuration-history entry.
    assert db.get_configuration(hardware_id) is None

def test_assign_missing_template(db):
    hardware_id = "AA:BB:CC:DD:EE:FF"

    db.register_device(hardware_id=hardware_id)

    with pytest.raises(ValueError):
        db.assign_template(hardware_id, "missing-template")


def test_assign_template_to_unknown_device(db):
    db.save_template(
        "temperature-monitor",
        "Temperature monitor",
        {"interval": 60}
    )

    with pytest.raises(ValueError):
        db.assign_template(
            "AA:BB:CC:DD:EE:FF",
            "temperature-monitor"
        )


def test_merge_config_overrides_values():
    template = {"interval": 60, "enabled": True}
    overrides = {"interval": 30}

    result = database.merge_config(template, overrides)

    assert result == {"interval": 30, "enabled": True}


def test_merge_config_nested_values():
    template = {
        "interval": 60,
        "mqtt": {
            "broker": "10.0.0.71",
            "port": 1883
        }
    }

    overrides = {
        "mqtt": {
            "port": 1884
        }
    }

    result = database.merge_config(template, overrides)

    assert result == {
        "interval": 60,
        "mqtt": {
            "broker": "10.0.0.71",
            "port": 1884
        }
    }


def test_merge_config_does_not_modify_originals():
    template = {"mqtt": {"port": 1883}}
    overrides = {"mqtt": {"port": 1884}}

    database.merge_config(template, overrides)

    assert template["mqtt"]["port"] == 1883
    assert overrides["mqtt"]["port"] == 1884

def test_effective_configuration_uses_template(db):
    hardware_id = "AA:BB:CC:DD:EE:FF"

    db.register_device(hardware_id=hardware_id)
    db.save_template("default", "Default template", {
        "interval": 60,
        "enabled": True
    })
    db.assign_template(hardware_id, "default")

    result = db.get_effective_configuration(hardware_id)

    assert result == {
        "interval": 60,
        "enabled": True
    }


def test_effective_configuration_applies_overrides(db):
    hardware_id = "AA:BB:CC:DD:EE:FF"

    db.register_device(hardware_id=hardware_id)
    db.save_template("default", "Default template", {
        "interval": 60,
        "mqtt": {
            "broker": "10.0.0.71",
            "port": 1883
        }
    })
    db.assign_template(hardware_id, "default")
    db.set_device_overrides(hardware_id, {
        "interval": 30,
        "mqtt": {
            "port": 1884
        }
    })

    result = db.get_effective_configuration(hardware_id)

    assert result == {
        "interval": 30,
        "mqtt": {
            "broker": "10.0.0.71",
            "port": 1884
        }
    }


def test_effective_configuration_unknown_device(db):
    result = db.get_effective_configuration("UNKNOWN")

    assert result is None


def test_template_update_preserves_device_overrides(db):
    hardware_id = "AA:BB:CC:DD:EE:FF"

    db.register_device(hardware_id=hardware_id)

    db.save_template("default", "Default template", {
        "interval": 60,
        "mqtt": {
            "broker": "10.0.0.71",
            "port": 1883
        }
    })

    db.assign_template(hardware_id, "default")

    db.set_device_overrides(hardware_id, {
        "interval": 30
    })

    # Update the template.
    db.save_template("default", "Default template", {
        "interval": 90,
        "mqtt": {
            "broker": "10.0.0.72",
            "port": 1883
        }
    })

    result = db.get_effective_configuration(hardware_id)

    assert result == {
        "interval": 30,
        "mqtt": {
            "broker": "10.0.0.72",
            "port": 1883
        }
    }

def test_config_version_increments_when_config_changes(db):
    hardware_id = "AA:BB:CC:DD:EE:FF"

    db.register_device(hardware_id=hardware_id)
    db.save_template("default", "Default template", {
        "interval": 60
    })
    db.assign_template(hardware_id, "default")

    previous = {"interval": 60}

    # Change the template.
    db.save_template("default", "Default template", {
        "interval": 90
    })

    version = db.get_device(hardware_id)["config_version"]

    assert version == 2

def test_config_version_does_not_increment_when_config_unchanged(db):
    hardware_id = "AA:BB:CC:DD:EE:FF"

    db.register_device(hardware_id=hardware_id)
    db.save_template("default", "Default template", {
        "interval": 60
    })
    db.assign_template(hardware_id, "default")

    previous = {"interval": 60}

    version = db.update_config_version(hardware_id, previous)

    assert version == 1

def test_template_update_increments_affected_device_versions(db):
    device_a = "AA:BB:CC:DD:EE:01"
    device_b = "AA:BB:CC:DD:EE:02"

    db.register_device(hardware_id=device_a)
    db.register_device(hardware_id=device_b)

    db.save_template("default", "Default template", {
        "interval": 60,
        "mqtt": {
            "broker": "10.0.0.71"
        }
    })

    db.assign_template(device_a, "default")
    db.assign_template(device_b, "default")

    # Device A overrides the interval.
    db.set_device_overrides(device_a, {
        "interval": 30
    })

    assert db.get_device(device_a)["config_version"] == 2
    assert db.get_device(device_b)["config_version"] == 1

    # Change both the interval and MQTT broker in the template.
    db.save_template("default", "Default template", {
        "interval": 90,
        "mqtt": {
            "broker": "10.0.0.72"
        }
    })

    assert db.get_device(device_a)["config_version"] == 3
    assert db.get_device(device_b)["config_version"] == 2

def test_assign_different_template_with_same_effective_config(db):
    hardware_id = "AA:BB:CC:DD:EE:FF"

    db.register_device(hardware_id=hardware_id)

    db.save_template(
        "default",
        "Default template",
        {"interval": 60}
    )

    db.save_template(
        "fast",
        "Fast sampling",
        {"interval": 10}
    )

    db.assign_template(hardware_id, "default")

    # Override the template's interval.
    db.set_device_overrides(
        hardware_id,
        {"interval": 120}
    )

    # Switching templates should not change the effective config.
    version = db.assign_template(hardware_id, "fast")

    assert version == 2

    config = db.get_effective_configuration(hardware_id)

    assert config == {"interval": 120}

def test_updating_template_only_changes_assigned_devices(db):
    device_a = "AA:BB:CC:DD:EE:01"
    device_b = "AA:BB:CC:DD:EE:02"

    db.register_device(hardware_id=device_a)
    db.register_device(hardware_id=device_b)

    db.save_template(
        "default",
        "Default template",
        {"interval": 60}
    )

    db.save_template(
        "fast",
        "Fast template",
        {"interval": 10}
    )

    db.assign_template(device_a, "default")
    db.assign_template(device_b, "fast")

    # Update only the default template.
    db.save_template(
        "default",
        "Default template",
        {"interval": 90}
    )

    assert db.get_device(device_a)["config_version"] == 2
    assert db.get_device(device_b)["config_version"] == 1

def test_updating_template_description_does_not_increment_version(db):
    hardware_id = "AA:BB:CC:DD:EE:FF"

    db.register_device(hardware_id=hardware_id)

    config = {"interval": 60}

    db.save_template(
        "default",
        "Original description",
        config
    )

    db.assign_template(hardware_id, "default")

    # Change only the description.
    db.save_template(
        "default",
        "Updated description",
        config
    )

    assert db.get_device(hardware_id)["config_version"] == 1

def test_updating_template_preserves_device_overrides(db):
    hardware_id = "AA:BB:CC:DD:EE:FF"

    db.register_device(hardware_id=hardware_id)

    db.save_template(
        "default",
        "Default template",
        {
            "interval": 60,
            "sensors": {
                "scd40": True,
                "ens160": True
            }
        }
    )

    db.assign_template(hardware_id, "default")

    db.set_device_overrides(
        hardware_id,
        {
            "interval": 120,
            "sensors": {
                "ens160": False
            }
        }
    )

    # Update the template, including a new default setting.
    db.save_template(
        "default",
        "Default template",
        {
            "interval": 30,
            "sensors": {
                "scd40": True,
                "ens160": True,
                "bme280": True
            }
        }
    )

    config = db.get_effective_configuration(hardware_id)

    assert config == {
        "interval": 120,
        "sensors": {
            "scd40": True,
            "ens160": False,
            "bme280": True
        }
    }

    assert db.get_device(hardware_id)["config_version"] == 3