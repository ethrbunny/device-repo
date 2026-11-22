
from flask import Blueprint, jsonify, request

import database

templates_bp = Blueprint("templates", __name__)


@templates_bp.route("/templates", methods=["GET"])
def list_templates():
    """Return all available templates."""

    templates = database.get_all_templates()

    return jsonify({
        "count": len(templates),
        "templates": templates
    })


@templates_bp.route("/templates/<name>", methods=["GET"])
def get_template(name):
    """Return a specific template."""

    template = database.get_template(name)

    if template is None:
        return jsonify({"error": "template_not_found"}), 404

    return jsonify(template)


@templates_bp.route("/templates", methods=["POST"])
def create_template():
    """Create or update a template."""

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "invalid_json"}), 400

    name = data.get("name")
    config = data.get("config")
    description = data.get("description", "")

    if not isinstance(name, str) or not name.strip():
        return jsonify({"error": "invalid_name"}), 400

    if not isinstance(config, dict):
        return jsonify({"error": "invalid_config"}), 400

    database.save_template(name, description, config)

    return jsonify({
        "status": "ok",
        "template": database.get_template(name)
    }), 201


@templates_bp.route(
    "/devices/<hardware_id>/template",
    methods=["PUT"]
)

def assign_device_template(hardware_id):
    """Assign a configuration template to a device."""

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "invalid_json"}), 400

    template_name = data.get("template")

    if isinstance(template_name, str):
        template_name = template_name.strip()

    if not isinstance(template_name, str) or not template_name.strip():
        return jsonify({"error": "invalid_template_name"}), 400

    try:
        version = database.assign_template(
            hardware_id,
            template_name
        )
    except ValueError as exc:
        message = str(exc)

        if message.startswith("Unknown device:"):
            return jsonify({"error": "unknown_device"}), 404

        return jsonify({"error": "template_not_found"}), 404

    return jsonify({
        "status": "ok",
        "hardware_id": hardware_id,
        "template": template_name,
        "config_version": version
    })

