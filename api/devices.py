
from flask import Blueprint, jsonify, request
import database

devices_bp = Blueprint("devices", __name__)

@devices_bp.route("/devices/<hardware_id>/config", methods=["GET"])
def get_device_config(hardware_id):
    """Return the effective configuration for a device."""

    device = database.get_device(hardware_id)

    if device is None:
        return jsonify({
            "error": "unknown_device",
            "hardware_id": hardware_id
        }), 404

    config = database.get_effective_configuration(hardware_id)

    if config is None:
        return jsonify({
            "error": "configuration_not_found",
            "hardware_id": hardware_id
        }), 404

    return jsonify({
        "hardware_id": hardware_id,
        "version": device["config_version"],
        "config": config
    })

@devices_bp.route("/devices/<hardware_id>/discover", methods=["POST"])
def discover_device(hardware_id):
    """Register or update a device when it checks in."""

    from flask import request

    data = request.get_json(silent=True) or {}

    firmware_version = data.get("firmware_version")

    device = database.discover_device(
        hardware_id,
        firmware_version=firmware_version
    )

    return jsonify({
        "status": "ok",
        "device": {
            "hardware_id": device["hardware_id"],
            "device_id": device["device_id"],
            "device_type": device["device_type"],
            "location": device["location"],
            "firmware_version": device["firmware_version"],
            "config_version": device["config_version"],
            "configured": device["template_name"] is not None
        }
    }), 200

@devices_bp.route("/devices/<hardware_id>/version", methods=["GET"])
def get_device_config_version(hardware_id):
    """Return the current configuration version for a device."""

    device = database.get_device(hardware_id)

    if device is None:
        return jsonify({
            "error": "unknown_device",
            "hardware_id": hardware_id
        }), 404

    return jsonify({
        "hardware_id": hardware_id,
        "version": device["config_version"]
    })

@devices_bp.route("/devices/<hardware_id>", methods=["PUT"])
def update_device(hardware_id):
    """Assign or update a device's identity and location."""

    from flask import request
    import sqlite3

    device = database.get_device(hardware_id)

    if device is None:
        return jsonify({
            "error": "unknown_device",
            "hardware_id": hardware_id
        }), 404

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "invalid_json"}), 400

    allowed_fields = {"device_id", "device_type", "location"}

    if not data or not set(data).issubset(allowed_fields):
        return jsonify({"error": "invalid_fields"}), 400

    try:
        database.register_device(
            hardware_id=hardware_id,
            device_id=data.get("device_id"),
            device_type=data.get("device_type"),
            location=data.get("location")
        )
    except sqlite3.IntegrityError:
        return jsonify({
            "error": "device_id_already_in_use"
        }), 409

    return jsonify({
        "status": "ok",
        "device": dict(database.get_device(hardware_id))
    })


@devices_bp.route("/devices", methods=["GET"])
def list_devices():
    """Return all registered devices."""

    devices = database.get_all_devices()

    return jsonify({
        "count": len(devices),
        "devices": devices
    })

@devices_bp.route("/devices/<hardware_id>/overrides", methods=["PUT"])
def update_device_overrides(hardware_id):
    """Update device-specific configuration overrides."""

    device = database.get_device(hardware_id)

    if device is None:
        return jsonify({
            "error": "unknown_device",
            "hardware_id": hardware_id
        }), 404

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "invalid_json"}), 400

    database.set_device_overrides(hardware_id, data)

    device = database.get_device(hardware_id)
    version = device["config_version"]

    return jsonify({
        "status": "ok",
        "hardware_id": hardware_id,
        "config_version": version,
        "overrides": data
    })