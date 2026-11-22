# Central Device Configuration Repository

A central configuration service for ESP32-C3 (Wi-Fi) and ESP32-H2 (Thread) devices.

The service maintains device registrations, shared configuration templates, device-specific overrides, and configuration versions in SQLite.

## 1. Service information

| Setting | Value |
|---|---|
| Service | `device-repo` |
| Server | `10.0.0.71` |
| Port | `5001` |
| API prefix | `/api/v1` |
| Database | `/var/lib/device-repo/devices.db` |
| Service account | `device-repo` |

Base URL:

```bash
BASE="http://10.0.0.71:5001/api/v1"
```

All API requests use JSON where a request body is required.

There is currently no authentication.

## 2. Device identification

Devices are identified by their hardware ID, obtained from the ESP32 eFuse MAC address.

Example:

```text
44:b1:76:08:cc:98
```

The hardware ID is the permanent device identity. The following are separate, assignable properties:

- `device_id`: Friendly device name
- `device_type`: Device category
- `location`: Physical location
- `firmware_version`: Running firmware version

## 3. Device API

### 3.1 Discover or register a device

```http
POST /api/v1/devices/<hardware_id>/discover
```

A device calls this when it starts and periodically checks in.

**Parameters**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `hardware_id` | URL string | Yes | ESP32 hardware MAC address |
| `firmware_version` | String | No | Current firmware version |

Example:

```bash
curl -X POST "$BASE/devices/44:b1:76:08:cc:98/discover" \
  -H "Content-Type: application/json" \
  -d '{
    "firmware_version": "1.0.0"
  }'
```

Discovery automatically registers an unknown device.

A registered device without an assigned template remains unconfigured.

### 3.2 Get a device configuration

```http
GET /api/v1/devices/<hardware_id>/config
```

Returns the effective configuration: the shared template recursively merged with device-specific overrides.

Example:

```bash
curl "$BASE/devices/44:b1:76:08:cc:98/config"
```

Example response:

```json
{
  "hardware_id": "44:b1:76:08:cc:98",
  "version": 6,
  "config": {
    "sensor": "sps30",
    "sampling_interval": 45,
    "location": "living-room",
    "mqtt": {
      "broker": "10.0.0.71",
      "port": 1883,
      "topic": "sensors/living-room/sps30"
    }
  }
}
```

Returns `404 configuration_not_found` if the device has no assigned configuration.

### 3.3 Get a device configuration version

```http
GET /api/v1/devices/<hardware_id>/version
```

Example:

```bash
curl "$BASE/devices/44:b1:76:08:cc:98/version"
```

Returns the device's current configuration version.

Devices can compare this version with their locally stored version to determine whether they need to download a new configuration.

### 3.4 Update device metadata

```http
PUT /api/v1/devices/<hardware_id>
```

Updates device metadata.

Example:

```bash
curl -X PUT "$BASE/devices/44:b1:76:08:cc:98" \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "living-room-sps30",
    "device_type": "air-quality-monitor",
    "location": "living-room",
    "firmware_version": "1.0.1"
  }'
```

Parameters:

| Parameter | Type | Description |
|---|---|---|
| `device_id` | String | Friendly device name |
| `device_type` | String | Device category |
| `location` | String | Physical location |
| `firmware_version` | String | Firmware version |

### 3.5 List all devices

```http
GET /api/v1/devices
```

Example:

```bash
curl "$BASE/devices"
```

Returns the registered devices and their metadata, including:

- Hardware ID
- Device ID
- Device type
- Location
- Firmware version
- Last seen
- Assigned template
- Configuration version
- Device overrides

## 4. Template API

Templates define shared configuration for a class of devices.

For example, all ESP32-C3 devices using an SPS30 sensor can share the `c3-sps30` template.

### 4.1 List all templates

```http
GET /api/v1/templates
```

Example:

```bash
curl "$BASE/templates"
```

### 4.2 Get a specific template

```http
GET /api/v1/templates/<name>
```

Example:

```bash
curl "$BASE/templates/c3-sps30"
```

### 4.3 Create or update a template

```http
POST /api/v1/templates
```

The template name is its unique identifier. Posting an existing name updates that template.

Parameters:

| Parameter | Type | Required | Description |
|---|---|---|---|
| `name` | String | Yes | Unique template name |
| `description` | String | No | Template description |
| `config` | Object | Yes | Shared configuration JSON |

Example:

```bash
curl -X POST "$BASE/templates" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "c3-sps30",
    "description": "ESP32-C3 with SPS30 particulate matter sensor",
    "config": {
      "sensor": "sps30",
      "sampling_interval": 45,
      "mqtt": {
        "broker": "10.0.0.71",
        "port": 1883
      }
    }
  }'
```

Updating a template changes the effective configuration version of devices assigned to it when their effective configuration actually changes.

## 5. Assign a template to a device

```http
PUT /api/v1/devices/<hardware_id>/template
```

Parameters:

| Parameter | Type | Required | Description |
|---|---|---|---|
| `template` | String | Yes | Name of the template to assign |

Example:

```bash
curl -X PUT "$BASE/devices/44:b1:76:08:cc:98/template" \
  -H "Content-Type: application/json" \
  -d '{
    "template": "c3-sps30"
  }'
```

The response includes the assigned template and configuration version.

Assigning a template does not increment the version if the effective configuration is unchanged.

## 6. Device-specific configuration overrides

Overrides allow individual devices to customize a shared template.

For example, all SPS30 devices can share the same MQTT broker and port, while each device publishes to a different topic.

### 6.1 Set device overrides

```http
PUT /api/v1/devices/<hardware_id>/overrides
```

The request body is a JSON object containing the device-specific settings.

Example:

```bash
curl -X PUT "$BASE/devices/44:b1:76:08:cc:98/overrides" \
  -H "Content-Type: application/json" \
  -d '{
    "location": "living-room",
    "mqtt": {
      "topic": "sensors/living-room/sps30"
    }
  }'
```

Overrides are recursively merged with the template.

For example, this template:

```json
{
  "sampling_interval": 45,
  "mqtt": {
    "broker": "10.0.0.71",
    "port": 1883
  }
}
```

Combined with these overrides:

```json
{
  "location": "living-room",
  "mqtt": {
    "topic": "sensors/living-room/sps30"
  }
}
```

Produces this effective configuration:

```json
{
  "sampling_interval": 45,
  "location": "living-room",
  "mqtt": {
    "broker": "10.0.0.71",
    "port": 1883,
    "topic": "sensors/living-room/sps30"
  }
}
```

The configuration version increments only when the effective configuration changes.

### 6.2 Read the effective configuration

After changing overrides, retrieve the complete configuration:

```bash
curl "$BASE/devices/44:b1:76:08:cc:98/config"
```

This is the configuration the device actually receives.

## 7. Typical administration workflow

### Register a new device

The device normally registers itself through discovery:

```bash
curl -X POST "$BASE/devices/44:b1:76:08:cc:98/discover" \
  -H "Content-Type: application/json" \
  -d '{"firmware_version":"1.0.0"}'
```

### Assign its template

```bash
curl -X PUT "$BASE/devices/44:b1:76:08:cc:98/template" \
  -H "Content-Type: application/json" \
  -d '{"template":"c3-sps30"}'
```

### Set its location and MQTT topic

```bash
curl -X PUT "$BASE/devices/44:b1:76:08:cc:98/overrides" \
  -H "Content-Type: application/json" \
  -d '{
    "location": "living-room",
    "mqtt": {
      "topic": "sensors/living-room/sps30"
    }
  }'
```

### Verify its configuration

```bash
curl "$BASE/devices/44:b1:76:08:cc:98/config"
```

### Check its configuration version

```bash
curl "$BASE/devices/44:b1:76:08:cc:98/version"
```

## 8. Configuration version behavior

Each device maintains its own configuration version.

| Operation | Version behavior |
|---|---|
| Assign template | Increments if effective configuration changes |
| Update template | Increments for affected devices if effective configuration changes |
| Update overrides | Increments if effective configuration changes |
| Repeat an unchanged update | Does not increment |
| Read configuration | Does not increment |
| Device discovery | Does not increment |

Devices should:

1. Discover themselves at startup.
2. Read the server's configuration version.
3. Download configuration when the server version differs from their local version.
4. Save the configuration locally.
5. Repeat the version check periodically.

The ESP32-C3 client currently checks every five minutes.

## 9. Service management

The repository runs as a systemd service on the Raspberry Pi.

Check status:

```bash
systemctl status device-repo
```

Start:

```bash
systemctl start device-repo
```

Stop:

```bash
systemctl stop device-repo
```

Restart:

```bash
systemctl restart device-repo
```

Enable at boot:

```bash
systemctl enable device-repo
```

View recent logs:

```bash
journalctl -u device-repo -n 50 --no-pager
```

Follow logs:

```bash
journalctl -u device-repo -f
```

## 10. Important paths

| Purpose | Path |
|---|---|
| Application | `/opt/device-repo/` |
| Database module | `/opt/device-repo/database.py` |
| Flask application | `/opt/device-repo/app.py` |
| Device API | `/opt/device-repo/api/devices.py` |
| Template API | `/opt/device-repo/api/templates.py` |
| Virtual environment | `/opt/device-repo/.venv/` |
| SQLite database | `/var/lib/device-repo/devices.db` |
| systemd service | `/etc/systemd/system/device-repo.service` |

The SQLite database should remain in `/var/lib/device-repo/`, separate from application code.

---

**Note:** This README documents the current HTTP API. ESP32-H2 devices use the separate Thread/UDP transport; they share the repository's configuration and database logic but do not use HTTP directly.