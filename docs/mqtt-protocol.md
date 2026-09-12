# MQTT Protocol — Edge <-> Platform

This document is the reference contract between the EMQX broker, the platform's
ingestion services, and edge devices (ESP32 gateways running the MicroPython
firmware in [`firmware/`](../firmware/)).

The platform side that implements this contract lives in
`platform/fmp/ingestion/main.py` (consumers) and `platform/fmp/ingestion/relay.py`
(command producer + ack consumer).

## 1. Transport

| Aspect | Value |
|--------|-------|
| Broker | EMQX 5.8 |
| TCP | `:1883` (plaintext, LAN only) |
| TLS | `:8883` (production; `ssl:cert_reqs = CERT_REQUIRED`) |
| Auth | Client username/password + optional mTLS client certificate |
| QoS | `1` (at-least-once) for every upload/downlink frame |

Messages are UTF-8 JSON. Every payload is schema-checked by the consumer; malformed
frames are logged and dropped without affecting other devices.

## 2. Gateway identity

Devices are addressed by `gateway_mac = "AA:BB:CC:DD:EE:01"` — the STA MAC address,
uppercase, colon-separated. Colons are legal in MQTT topic segments.

The gateway publishes its own identity on every status frame. The platform
auto-registers an `IoTGateway` row on the first status frame
(`is_active = false` until a human activates it).

Tank association happens Server-side, in order:

1. `gateway_mac` + `sensor_serial_number` (cached lookup)
2. `tank_id` field carried on a legacy frame
3. `Tank.sensor_serial_number == serial`
4. `Tank.gateway_mac == mac`

So a tank must exist with `gateway_mac` **or** `sensor_serial_number` set before
its frames will persist. Unknown devices are negative-cached to avoid DB churn.

## 3. Topics

| Direction | Topic pattern | QoS | Meaning |
|-----------|---------------|-----|---------|
| device → broker | `fuel/<mac>/readings` | 1 | Tank level sensor frame |
| device → broker | `fuel/<mac>/status` | 1 | Heartbeat / online diagnostics |
| device → broker | `fuel/<mac>/command/ack` | 1 | Command correlation reply |
| broker → device | `fuel/<mac>/command` | 1 | Command issued by platform |

The device **subscribes** to `fuel/<mac>/command`; the platform **subscribes** to
`fuel/+/readings`, `fuel/+/status`, `fuel/+/command/ack`.

A device may also publish readings on the legacy `ingestion/readings` and
`ingestion/status` topics; the same consumers handle them. Commands are only ever
addressed per-device.

## 4. Readings (`fuel/<mac>/readings`)

```json
{
  "gateway_mac": "AA:BB:CC:DD:EE:01",
  "sensor_serial_number": "SS-010203040506",
  "measurement": {
    "timestamp": "2026-09-12T14:00:00+00:00",
    "pressure": 0.7362,
    "temperature": 24.5,
    "status": 0
  }
}
```

The `measurement` wrapper is optional; a flat frame with the same inner fields at
top level is accepted (`pressure`, `temperature`, `status`, `timestamp` directly).

| Field | Type | Required | Meaning |
|-------|------|----------|---------|
| `gateway_mac` | string | note | Uppercase colon MAC. Preferred; the topic MAC is the fallback |
| `sensor_serial_number` | string | note | e.g. `SS-<hex>`; ties frame to a tank row |
| `measurement.timestamp` | ISO-8601 | no | Capture time (`Z` or `+00:00`); platform uses `utcnow()` if absent/invalid |
| `measurement.pressure` | float | no | **bar**; drives the whole level/volume pipeline. Defaults `0.0` |
| `measurement.temperature` | float | no | °C; used for density/temperature correction |
| `measurement.status` | int | no | sensor status bitmask; `0` = nominal |

Units are important: the platform computes `level → volume → fill_percent` from
`pressure` (bar) using each tank's calibration, geometry and fuel density. The
firmware must convert its physical reading (see `firmware/level_sensor.py`) so the
frame carries **pressure in bar**, not raw probe counts.

## 5. Status (`fuel/<mac>/status`)

```json
{
  "status": "online",
  "firmware_version": "1.0.0",
  "timestamp": "2026-09-12T14:00:00+00:00",
  "uptime_s": 86400,
  "rssi_dbm": -55
}
```

| Field | Type | Required | Meaning |
|-------|------|----------|---------|
| `status` | string | yes | `"online"` (or `"offline"` in LWT) |
| `firmware_version` | string | no | recorded on the gateway row |
| `timestamp` | ISO-8601 | no | heartbeat time |
| `uptime_s` / `rssi_dbm` | number | no | diagnostics (optional) |

Sent once per MQTT connect and periodically. The consumer marks the matching tank,
its station and the gateway online.

## 6. Commands (`fuel/<mac>/command`)

Published by the platform on `fuel/<mac>/command`:

```json
{
  "command_id": "3f2e7d31-38d0-4b97-a7b0-ec4f3f7b0001",
  "type": "status_probe",
  "payload": {},
  "issued_at": "2026-09-12T14:00:00+00:00",
  "attempts": 1
}
```

| Field | Type | Meaning |
|-------|------|---------|
| `command_id` | uuid string | unique correlation key; echo unchanged in the ack |
| `type` | string | command type (see below) |
| `payload` | object | type-specific arguments |
| `issued_at` | ISO-8601 | issue time |
| `attempts` | int | delivery attempt counter (relay bumps each retry) |

Delivery is at-least-once: a frame may arrive multiple times (broker retry + the
relay sweeper re-publishing on timeout). **The device must be idempotent** — commands
with the same `command_id` are acknowledged once and the effect applied once.

### Supported types

| `type` | payload | effect | ack detail |
|--------|---------|--------|------------|
| `ping` | — | no-op (keepalive probe) | `"ping ok"` |
| `status_probe` | — | publish a fresh status frame | system snapshot (uptime, rssi, reset cause) |
| `set_interval` | `{"seconds": 30}` | change sampling interval (clamped `5..3600`) | `"sampling interval now 30 s"` |
| `reboot` | — | clean reboot | `"rebooting"` (send ack *before* reset) |

Unknown `type` → ack `"rejected"` with `detail` naming the type.

## 7. Command acks (`fuel/<mac>/command/ack`)

```json
{
  "command_id": "3f2e7d31-38d0-4b97-a7b0-ec4f3f7b0001",
  "status": "executed",
  "detail": "uptime_s=3600"
}
```

| Field | Type | Meaning |
|-------|------|---------|
| `command_id` | string | must match the received command |
| `status` | string | `"executed"` or `"rejected"` only |
| `detail` | string | optional free-form note |

On `executed` the platform marks the command `acked`; on `rejected` it marks it
`rejected` and stops retrying. Malformed acks (missing id, unknown status) are
dropped.

## 8. Offline behavior

Power loss, WiFi drop, or broker loss must not lose readings:

1. Every produced reading is appended to a bounded flash buffer (`frame_buffer.py`)
   regardless of connectivity.
2. On MQTT (re)connect the device:
   - publishes a fresh `status` frame;
   - re-subscribes to `fuel/<mac>/command`;
   - replays buffered readings in order over `fuel/<mac>/readings`, then clears
     the buffer.
3. Optional fallback: when the broker stays unreachable, buffered frames can be
   POSTed to the ingestion HTTP API `POST /api/v1/ingest/backfill`
   `[frame, ...]` (config-gated, see `firmware/config_example.py`).

The buffer is bounded (`max_frames` / `max_bytes`); oldest frames are trimmed first.

## 9. Example flow

```
[ESP32]  frame = {gateway_mac, sensor_serial_number, measurement:{pressure,...}}
[ESP32]  PUBLISH fuel/AA:BB:CC:DD:EE:01/readings        (QoS 1)
[Broker] -> platform fuel/+/readings handler
[Platform] resolve tank -> calibrate -> level/volume -> TimescaleDB + Redis live feed

[Platform] relay: PUBLISH fuel/AA:BB:CC:DD:EE:01/command  {command_id, type, ...}
[ESP32]  SUBSCRIBE fuel/AA:BB:CC:DD:EE:01/command
[ESP32]  apply effect (idempotent), then
[ESP32]  PUBLISH fuel/AA:BB:CC:DD:EE:01/command/ack       {command_id, status:"executed"}
[Platform] mark GatewayCommand acked -> sweep stops retrying
```

## 10. Related / legacy notes

- The 2022-era archive describes a legacy protocol on `fuel/<mac>/cmd` (singular)
  with a flat `sensors[]` array; that is historical only. Devices must speak the
  current `command` / `command/ack` contract above.
- `TECHNICAL_SPECIFICATION.md` tables that mention `fuel/{mac}/commands` and
  `fuel/{mac}/errors` are likewise superseded by the topics in §3.