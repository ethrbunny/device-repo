
import pytest
import database
from app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(
        database,
        "DB_PATH",
        tmp_path / "devices.db"
    )

    database.initialize_database()

    app = create_app()
    app.config["TESTING"] = True

    return app.test_client()


def test_create_template(client):
    response = client.post(
        "/api/v1/templates",
        json={
            "name": "air-quality-monitor",
            "description": "Indoor air quality monitor",
            "config": {"interval": 60}
        }
    )

    assert response.status_code == 201
    assert response.get_json()["template"]["config"]["interval"] == 60


def test_get_template(client):
    database.save_template(
        "temperature-monitor",
        "Temperature monitor",
        {"interval": 120}
    )

    response = client.get(
        "/api/v1/templates/temperature-monitor"
    )

    assert response.status_code == 200
    assert response.get_json()["config"]["interval"] == 120


def test_get_missing_template(client):
    response = client.get("/api/v1/templates/missing")

    assert response.status_code == 404


def test_list_templates(client):
    database.save_template("template-a", "First", {"interval": 60})
    database.save_template("template-b", "Second", {"interval": 120})

    response = client.get("/api/v1/templates")

    assert response.status_code == 200
    assert response.get_json()["count"] == 2


def test_assign_template_to_device(client):
    hardware_id = "AA:BB:CC:DD:EE:FF"

    database.register_device(hardware_id=hardware_id)

    database.save_template(
        "air-quality-monitor",
        "Indoor air quality monitor",
        {"interval": 60}
    )

    response = client.put(
        f"/api/v1/devices/{hardware_id}/template",
        json={"template": "air-quality-monitor"}
    )

    assert response.status_code == 200

    data = response.get_json()
    assert data["status"] == "ok"

    device = database.get_device(hardware_id)
    assert device["template_name"] == "air-quality-monitor"

    assert database.get_configuration(hardware_id) is None

def test_assign_missing_template(client):
    hardware_id = "AA:BB:CC:DD:EE:FF"

    database.register_device(hardware_id=hardware_id)

    response = client.put(
        f"/api/v1/devices/{hardware_id}/template",
        json={"template": "missing"}
    )

    assert response.status_code == 404


def test_assign_template_to_unknown_device(client):
    database.save_template(
        "temperature-monitor",
        "Temperature monitor",
        {"interval": 120}
    )

    response = client.put(
        "/api/v1/devices/11:22:33:44:55:66/template",
        json={"template": "temperature-monitor"}
    )

    assert response.status_code == 404

