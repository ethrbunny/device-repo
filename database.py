
import sqlite3
from pathlib import Path
import json
from datetime import datetime, timezone

# Keep the database in the project's data directory.
PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"
DB_PATH = DATA_DIR / "devices.db"



def get_connection():
    """Open a connection to the device repository database."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def initialize_database():
    """Create the database tables if they don't already exist."""

    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS devices (
                hardware_id TEXT PRIMARY KEY,
                device_id TEXT UNIQUE,
                device_type TEXT,
                location TEXT,
                firmware_version TEXT,
                last_seen TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                template_name TEXT,
                overrides_json TEXT NOT NULL DEFAULT '{}',
                config_version INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS configurations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hardware_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                config_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (hardware_id)
                REFERENCES devices (hardware_id),
                UNIQUE (hardware_id, version)
            );

            CREATE TABLE IF NOT EXISTS templates (
                name TEXT PRIMARY KEY,
                description TEXT,
                config_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """)
    # Upgrade existing databases if necessary
    with get_connection() as conn:
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(devices)")
        }

        if "template_name" not in columns:
            conn.execute(
                "ALTER TABLE devices ADD COLUMN template_name TEXT"
            )

        if "overrides_json" not in columns:
            conn.execute(
                "ALTER TABLE devices ADD COLUMN "
                "overrides_json TEXT NOT NULL DEFAULT '{}'"
            )

        if "config_version" not in columns:
            conn.execute(
                "ALTER TABLE devices ADD COLUMN "
                "config_version INTEGER NOT NULL DEFAULT 0"
            )

if __name__ == "__main__":
    initialize_database()
    print(f"Database initialized: {DB_PATH}")

def register_device(hardware_id, device_id=None, device_type=None, location=None):
    """Register a new device, or update its identifying information."""

    with get_connection() as conn:
        conn.execute("""
            INSERT INTO devices (
                hardware_id, device_id, device_type, location
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(hardware_id) DO UPDATE SET
                device_id = COALESCE(excluded.device_id, devices.device_id),
                device_type = COALESCE(excluded.device_type, devices.device_type),
                location = COALESCE(excluded.location, devices.location)
        """, (hardware_id, device_id, device_type, location))


def get_device(hardware_id):
    """Return a device record, or None if it isn't registered."""

    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM devices WHERE hardware_id = ?",
            (hardware_id,)
        ).fetchone()


def save_configuration(hardware_id, config):
    """Save a new configuration version for a device."""

    config_json = json.dumps(config, indent=2)

    with get_connection() as conn:
        device = conn.execute(
            "SELECT hardware_id FROM devices WHERE hardware_id = ?",
            (hardware_id,)
        ).fetchone()

        if device is None:
            raise ValueError(f"Unknown device: {hardware_id}")

        current = conn.execute("""
            SELECT MAX(version) AS version
            FROM configurations
            WHERE hardware_id = ?
        """, (hardware_id,)).fetchone()

        version = (current["version"] or 0) + 1

        conn.execute("""
            INSERT INTO configurations (
                hardware_id, version, config_json
            )
            VALUES (?, ?, ?)
        """, (hardware_id, version, config_json))

    return version


def get_configuration(hardware_id):
    """Return the latest configuration and its version."""

    with get_connection() as conn:
        row = conn.execute("""
            SELECT version, config_json
            FROM configurations
            WHERE hardware_id = ?
            ORDER BY version DESC
            LIMIT 1
        """, (hardware_id,)).fetchone()

        if row is None:
            return None

        return {
            "version": row["version"],
            "config": json.loads(row["config_json"])
        }


def update_device_status(hardware_id, firmware_version=None):
    """Record that a device has checked in."""

    now = datetime.now(timezone.utc).isoformat()

    with get_connection() as conn:
        conn.execute("""
            UPDATE devices
            SET last_seen = ?,
                firmware_version = COALESCE(?, firmware_version)
            WHERE hardware_id = ?
        """, (now, firmware_version, hardware_id))


def discover_device(hardware_id, firmware_version=None):
    """Register an unknown device or update an existing device's last_seen."""

    now = datetime.now(timezone.utc).isoformat()

    with get_connection() as conn:
        conn.execute("""
            INSERT INTO devices (
                hardware_id,
                firmware_version,
                last_seen
            )
            VALUES (?, ?, ?)
            ON CONFLICT(hardware_id) DO UPDATE SET
                last_seen = excluded.last_seen,
                firmware_version = COALESCE(
                    excluded.firmware_version,
                    devices.firmware_version
                )
        """, (hardware_id, firmware_version, now))

        row = conn.execute("""
            SELECT * FROM devices
            WHERE hardware_id = ?
        """, (hardware_id,)).fetchone()

        return dict(row)


def get_all_devices():
    """Return all registered devices."""

    with get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM devices
            ORDER BY device_id, hardware_id
        """).fetchall()

        return [dict(row) for row in rows]
def save_template(name, description, config):
    """Create or replace a configuration template."""

    # Capture current effective configurations for assigned devices.
    with get_connection() as conn:
        devices = conn.execute(
            """
            SELECT hardware_id
            FROM devices
            WHERE template_name = ?
            """,
            (name,)
        ).fetchall()

    previous_configs = {
        device["hardware_id"]: get_effective_configuration(
            device["hardware_id"]
        )
        for device in devices
    }

    # Create or update the template.
    config_json = json.dumps(config, indent=2)

    with get_connection() as conn:
        conn.execute("""
            INSERT INTO templates (name, description, config_json)
            VALUES (?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                description = excluded.description,
                config_json = excluded.config_json
        """, (name, description, config_json))

    # Update versions for devices whose effective config changed.
    for hardware_id, previous_config in previous_configs.items():
        update_config_version(hardware_id, previous_config)

def get_template(name):
    """Retrieve a configuration template."""

    with get_connection() as conn:
        row = conn.execute("""
            SELECT * FROM templates
            WHERE name = ?
        """, (name,)).fetchone()

        if row is None:
            return None

        return {
            "name": row["name"],
            "description": row["description"],
            "config": json.loads(row["config_json"])
        }

def assign_template(hardware_id, template_name):
    """Assign a configuration template to a device."""

    template = get_template(template_name)

    if template is None:
        raise ValueError(f"Unknown template: {template_name}")

    if get_device(hardware_id) is None:
        raise ValueError(f"Unknown device: {hardware_id}")

    previous_config = get_effective_configuration(hardware_id)

    with get_connection() as conn:
        conn.execute(
            """
            UPDATE devices
            SET template_name = ?
            WHERE hardware_id = ?
            """,
            (template_name, hardware_id)
        )

    version = update_config_version(hardware_id, previous_config)

    return version

def get_all_templates():
    """Return all configuration templates."""

    with get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM templates
            ORDER BY name
        """).fetchall()

        return [
            {
                "name": row["name"],
                "description": row["description"],
                "config": json.loads(row["config_json"])
            }
            for row in rows
        ]


def merge_config(template_config, device_overrides):
    """Recursively merge device overrides into template defaults."""

    result = template_config.copy()

    for key, value in device_overrides.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = merge_config(result[key], value)
        else:
            result[key] = value

    return result

def set_device_overrides(hardware_id, overrides):
    """Save device-specific configuration overrides."""

    if get_device(hardware_id) is None:
        raise ValueError(f"Unknown device: {hardware_id}")

    if not isinstance(overrides, dict):
        raise ValueError("Overrides must be a dictionary")

    previous_config = get_effective_configuration(hardware_id)

    with get_connection() as conn:
        conn.execute(
            """
            UPDATE devices
            SET overrides_json = ?
            WHERE hardware_id = ?
            """,
            (json.dumps(overrides), hardware_id)
        )

    update_config_version(hardware_id, previous_config)

    return True

def get_effective_configuration(hardware_id):
    """Return the merged template and device configuration."""

    device = get_device(hardware_id)

    if device is None:
        return None

    template_name = device["template_name"]

    if template_name is None:
        return None

    template = get_template(template_name)

    if template is None:
        return None

    overrides = json.loads(device["overrides_json"])

    return merge_config(template["config"], overrides)

def update_config_version(hardware_id, previous_config):
    """Increment version if effective configuration has changed."""

    current_config = get_effective_configuration(hardware_id)

    if current_config is None:
        return None

    if current_config != previous_config:
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE devices
                SET config_version = config_version + 1
                WHERE hardware_id = ?
                """,
                (hardware_id,)
            )

    device = get_device(hardware_id)
    return device["config_version"]