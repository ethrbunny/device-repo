
import pytest
import database
from app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    test_db = tmp_path / "devices.db"
    monkeypatch.setattr(database, "DB_PATH", test_db)

    database.initialize_database()

    app = create_app()
    app.config["TESTING"] = True

    return app.test_client()


def test_get_device_config(client):
    hardware_id = "AA:BB:CC:DD:EE:FF"

    database.register_device(hardware_id=hardware_id)

    database.save_template(
        "default",
        "Default template",
        {
            "interval": 60,
            "sensors": {
                "scd40": True
            }
        }
    )

    database.assign_template(hardware_id, "default")

    response = client.get(
        f"/api/v1/devices/{hardware_id}/config"
    )

    assert response.status_code == 200

    data = response.get_json()

    assert data["hardware_id"] == hardware_id
    assert data["version"] == 1
    assert data["config"] == {
        "interval": 60,
        "sensors": {
            "scd40": True
        }
    }

def test_unknown_device(client):
    response = client.get(
        "/api/v1/devices/11:22:33:44:55:66/config"
    )

    assert response.status_code == 404
    assert response.get_json()["error"] == "unknown_device"


def test_discover_existing_device(client):
    hardware_id = "AA:BB:CC:DD:EE:FF"

    database.register_device(
        hardware_id=hardware_id,
        device_id="office-sensor",
        device_type="air-quality-monitor",
        location="office"
    )

    response = client.post(
        f"/api/v1/devices/{hardware_id}/discover",
        json={"firmware_version": "1.1.0"}
    )

    assert response.status_code == 200

    device = response.get_json()["device"]

    assert device["device_id"] == "office-sensor"
    assert device["location"] == "office"
    assert device["firmware_version"] == "1.1.0"


def test_get_config_version(client):
    hardware_id = "AA:BB:CC:DD:EE:FF"

    database.register_device(hardware_id=hardware_id)

    database.save_template(
        "default",
        "Default template",
        {"interval": 60}
    )

    database.assign_template(hardware_id, "default")

    response = client.get(
        f"/api/v1/devices/{hardware_id}/version"
    )

    assert response.status_code == 200
    assert response.get_json()["version"] == 1

    # Updating the template should increment the device version.
    database.save_template(
        "default",
        "Default template",
        {"interval": 90}
    )

    response = client.get(
        f"/api/v1/devices/{hardware_id}/version"
    )

    assert response.get_json()["version"] == 2

def test_get_config_version_without_config(client):
    hardware_id = "11:22:33:44:55:66"

    database.discover_device(hardware_id)

    response = client.get(
        f"/api/v1/devices/{hardware_id}/version"
    )

    assert response.status_code == 200
    assert response.get_json()["version"] == 0


def test_assign_device(client):
    hardware_id = "AA:BB:CC:DD:EE:FF"

    database.discover_device(hardware_id)

    response = client.put(
        f"/api/v1/devices/{hardware_id}",
        json={
            "device_id": "office-air-quality-01",
            "device_type": "air-quality-monitor",
            "location": "office"
        }
    )

    assert response.status_code == 200

    device = response.get_json()["device"]

    assert device["device_id"] == "office-air-quality-01"
    assert device["device_type"] == "air-quality-monitor"
    assert device["location"] == "office"


def test_assign_unknown_device(client):
    response = client.put(
        "/api/v1/devices/11:22:33:44:55:66",
        json={"device_id": "unknown-device"}
    )

    assert response.status_code == 404


def test_duplicate_device_id(client):
    database.register_device(
        hardware_id="AA:BB:CC:DD:EE:FF",
        device_id="office-sensor"
    )

    database.discover_device("11:22:33:44:55:66")

    response = client.put(
        "/api/v1/devices/11:22:33:44:55:66",
        json={"device_id": "office-sensor"}
    )

    assert response.status_code == 409


def test_list_devices(client):
    database.register_device(
        hardware_id="AA:BB:CC:DD:EE:FF",
        device_id="office-sensor",
        location="office"
    )

    database.discover_device(
        "11:22:33:44:55:66",
        firmware_version="1.0.0"
    )

    response = client.get("/api/v1/devices")

    assert response.status_code == 200

    data = response.get_json()

    assert data["count"] == 2
    assert len(data["devices"]) == 2


def test_list_devices_empty(client):
    response = client.get("/api/v1/devices")

    assert response.status_code == 200

    data = response.get_json()

    assert data["count"] == 0
    assert data["devices"] == []

def test_get_device_config_includes_overrides(client):
    hardware_id = "AA:BB:CC:DD:EE:FF"

    database.register_device(hardware_id=hardware_id)

    database.save_template(
        "default",
        "Default template",
        {
            "interval": 60,
            "sensors": {
                "scd40": True,
                "bme280": True
            }
        }
    )

    database.assign_template(hardware_id, "default")

    database.set_device_overrides(
        hardware_id,
        {
            "interval": 120,
            "sensors": {
                "bme280": False
            }
        }
    )

    response = client.get(
        f"/api/v1/devices/{hardware_id}/config"
    )

    assert response.status_code == 200

    data = response.get_json()

    assert data["version"] == 2
    assert data["config"] == {
        "interval": 120,
        "sensors": {
            "scd40": True,
            "bme280": False
        }
    }

def test_unchanged_overrides_do_not_increment_version(client):
    hardware_id = "AA:BB:CC:DD:EE:FF"

    database.register_device(hardware_id=hardware_id)

    database.save_template(
        "default",
        "Default template",
        {"interval": 60}
    )

    database.assign_template(hardware_id, "default")

    database.set_device_overrides(
        hardware_id,
        {"interval": 120}
    )

    # Apply the exact same override again.
    database.set_device_overrides(
        hardware_id,
        {"interval": 120}
    )

    response = client.get(
        f"/api/v1/devices/{hardware_id}/version"
    )

    assert response.status_code == 200
    assert response.get_json()["version"] == 2

def test_get_device_config_without_template(client):
    hardware_id = "AA:BB:CC:DD:EE:FF"

    database.register_device(hardware_id=hardware_id)

    response = client.get(
        f"/api/v1/devices/{hardware_id}/config"
    )

    assert response.status_code == 404
    assert response.get_json() == {
        "error": "configuration_not_found",
        "hardware_id": hardware_id
    }

def test_assign_device_template_returns_config_version(client):
    hardware_id = "AA:BB:CC:DD:EE:FF"

    database.register_device(hardware_id=hardware_id)

    database.save_template(
        "default",
        "Default template",
        {"interval": 60}
    )

    response = client.put(
        f"/api/v1/devices/{hardware_id}/template",
        json={"template": "default"}
    )

    assert response.status_code == 200

    data = response.get_json()

    assert data["status"] == "ok"
    assert data["hardware_id"] == hardware_id
    assert data["template"] == "default"
    assert data["config_version"] == 1

def test_reassign_same_template_does_not_increment_version(client):
    hardware_id = "AA:BB:CC:DD:EE:FF"

    database.register_device(hardware_id=hardware_id)

    database.save_template(
        "default",
        "Default template",
        {"interval": 60}
    )

    url = f"/api/v1/devices/{hardware_id}/template"

    first_response = client.put(
        url,
        json={"template": "default"}
    )

    assert first_response.status_code == 200
    assert first_response.get_json()["config_version"] == 1

    second_response = client.put(
        url,
        json={"template": "default"}
    )

    assert second_response.status_code == 200
    assert second_response.get_json()["config_version"] == 1

def test_assign_different_template_increments_version(client):
    hardware_id = "AA:BB:CC:DD:EE:FF"

    database.register_device(hardware_id=hardware_id)

    database.save_template(
        "default",
        "Default template",
        {"interval": 60}
    )

    database.save_template(
        "fast",
        "Fast sampling",
        {"interval": 10}
    )

    url = f"/api/v1/devices/{hardware_id}/template"

    first_response = client.put(
        url,
        json={"template": "default"}
    )

    assert first_response.status_code == 200
    assert first_response.get_json()["config_version"] == 1

    second_response = client.put(
        url,
        json={"template": "fast"}
    )

    assert second_response.status_code == 200
    assert second_response.get_json()["config_version"] == 2

def test_discover_new_device(client):
    hardware_id = "AA:BB:CC:DD:EE:FF"

    response = client.post(
        f"/api/v1/devices/{hardware_id}/discover",
        json={"firmware_version": "1.0.0"}
    )

    assert response.status_code == 200

    data = response.get_json()

    assert data["status"] == "ok"
    assert data["device"]["hardware_id"] == hardware_id
    assert data["device"]["firmware_version"] == "1.0.0"
    assert data["device"]["config_version"] == 0
    assert data["device"]["configured"] is False
    assert data["device"]["device_id"] is None
    assert data["device"]["device_type"] is None
    assert data["device"]["location"] is None

def test_rediscover_existing_device_preserves_configuration(client):
    hardware_id = "AA:BB:CC:DD:EE:FF"

    # Discover the device.
    client.post(
        f"/api/v1/devices/{hardware_id}/discover",
        json={"firmware_version": "1.0.0"}
    )

    # Assign its identity and location.
    response = client.put(
        f"/api/v1/devices/{hardware_id}",
        json={
            "device_id": "h2-01",
            "device_type": "esp32-h2",
            "location": "test"
        }
    )
    assert response.status_code == 200

    # Assign a configuration template.
    database.save_template(
        "default",
        "Default template",
        {"interval": 60}
    )
    database.assign_template(hardware_id, "default")

    # Discover it again with newer firmware.
    response = client.post(
        f"/api/v1/devices/{hardware_id}/discover",
        json={"firmware_version": "1.1.0"}
    )

    assert response.status_code == 200

    device = response.get_json()["device"]

    assert device["firmware_version"] == "1.1.0"
    assert device["device_id"] == "h2-01"
    assert device["device_type"] == "esp32-h2"
    assert device["location"] == "test"
    assert device["config_version"] == 1
    assert device["configured"] is True

def test_rediscover_updates_last_seen(client):
    hardware_id = "AA:BB:CC:DD:EE:FF"

    # First discovery.
    client.post(
        f"/api/v1/devices/{hardware_id}/discover",
        json={"firmware_version": "1.0.0"}
    )

    first_seen = database.get_device(hardware_id)["last_seen"]

    # Rediscover the device.
    client.post(
        f"/api/v1/devices/{hardware_id}/discover",
        json={"firmware_version": "1.0.1"}
    )

    second_seen = database.get_device(hardware_id)["last_seen"]

    assert second_seen >= first_seen

def test_update_device_overrides(client):
    hardware_id = "AA:BB:CC:DD:EE:FF"

    database.register_device(hardware_id=hardware_id)

    database.save_template(
        "c3-sps30",
        "SPS30 template",
        {
            "sampling_interval": 45,
            "mqtt": {
                "broker": "10.0.0.71",
                "port": 1883
            }
        }
    )

    database.assign_template(hardware_id, "c3-sps30")

    response = client.put(
        f"/api/v1/devices/{hardware_id}/overrides",
        json={
            "location": "living-room",
            "mqtt": {
                "topic": "sensors/living-room/sps30"
            }
        }
    )

    assert response.status_code == 200

    data = response.get_json()

    assert data["status"] == "ok"
    assert data["hardware_id"] == hardware_id
    assert data["config_version"] == 2

def test_update_overrides_unknown_device(client):
    response = client.put(
        "/api/v1/devices/11:22:33:44:55:66/overrides",
        json={"location": "bedroom"}
    )

    assert response.status_code == 404
    assert response.get_json()["error"] == "unknown_device"


def test_update_overrides_invalid_json(client):
    hardware_id = "AA:BB:CC:DD:EE:FF"

    database.register_device(hardware_id=hardware_id)

    response = client.put(
        f"/api/v1/devices/{hardware_id}/overrides",
        data="not json",
        content_type="application/json"
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_json"

def test_update_overrides_changes_effective_config(client):
    hardware_id = "AA:BB:CC:DD:EE:FF"

    database.register_device(hardware_id=hardware_id)

    database.save_template(
        "c3-sps30",
        "SPS30 template",
        {
            "sampling_interval": 45,
            "mqtt": {
                "broker": "10.0.0.71",
                "port": 1883
            }
        }
    )

    database.assign_template(hardware_id, "c3-sps30")

    response = client.put(
        f"/api/v1/devices/{hardware_id}/overrides",
        json={
            "location": "living-room",
            "mqtt": {
                "topic": "sensors/living-room/sps30"
            }
        }
    )

    assert response.status_code == 200

    response = client.get(
        f"/api/v1/devices/{hardware_id}/config"
    )

    assert response.status_code == 200

    data = response.get_json()

    assert data["config"] == {
        "sampling_interval": 45,
        "location": "living-room",
        "mqtt": {
            "broker": "10.0.0.71",
            "port": 1883,
            "topic": "sensors/living-room/sps30"
        }
    }

    assert data["version"] == 2