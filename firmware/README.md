# ESP32 Edge Gateway Firmware

MicroPython firmware for the tank-level-sensor ESP32 gateway. Implements the
wire protocol in [`docs/mqtt-protocol.md`](../docs/mqtt-protocol.md).

## Hardware

- **MCU**: ESP32 (any MicroPython-capable variant; 4 MB flash minimum)
- **RS-485 transceiver**: MAX3485 (or compatible) — `TX`/`RX` via `UART1`, `DE`/`RE` direct-driven by one GPIO
- **Sensor**: any RS-485 Modbus RTU level / hydrostatic pressure gauge
- **Power**: 5–12 V input regulated to 3.3 V for the ESP32

## Flashing

Using [mpremote](https://micropython.com/download/mpremote) (recommended):

```bash
# one-time provision
mpremote cp firmware/*.py :/

# or full re-flash (preserves /config.py)
mpremote cp firmware/main.py :/ \
           firmware/boot.py :/ \
           firmware/device.py :/ \
           firmware/nettime.py :/ \
           firmware/wifi.py :/ \
           firmware/mqtt_client.py :/ \
           firmware/rs485.py :/ \
           firmware/backfill.py :/ \
           firmware/modbus_rtu.py :/ \
           firmware/level_sensor.py :/ \
           firmware/frames.py :/ \
           firmware/frame_buffer.py :/ \
           firmware/commands.py :/

mpremote run firmware/main.py
```

## Configuration

Copy `config_example.py` to the device as `config.py` and fill in secrets.
All sensor channel maps, MQTT credentials, and pin assignments live there.

If `config.py` is absent, safe defaults are used but the gateway is useless
without WiFi credentials.

## TLS Provisioning

For production (`MQTT_TLS = True`) place the following on the device filesystem:

| Path | Contents |
|------|----------|
| `/certs/ca.pem` | Broker CA certificate (PEM) |
| `/certs/client.pem` | Client certificate (PEM) — only if mTLS is required |
| `/certs/client.key` | Client private key (PEM) — only if mTLS is required |

Files can be copied with `mpremote`:

```bash
mpremote cp certs/ca.pem :/certs/ca.pem \
           certs/client.pem :/certs/client.pem \
           certs/client.key :/certs/client.key
```

## Online debug

```bash
# REPL session (see live output + watch logs)
mpremote repl

# or stream print output only
mpremote run firmware/main.py
```

## Testing

The pure-logic modules (`modbus_rtu`, `level_sensor`, `frames`, `frame_buffer`,
`commands`) have no MicroPython dependencies and run on any Python 3.9+ host.

```bash
python3 -m pytest firmware/tests/
```

Test coverage: CRC-16 vectors, Modbus request/response codecs, level→pressure
conversions, frame JSON shapes, offline buffer trim, command idempotency and
unknown-type rejection.

## Firmware protocol implementation

| Module | Role |
|--------|------|
| `main.py` | Orchestration: WiFi → NTP → poll → MQTT → command loop |
| `modbus_rtu.py` | Pure CRC-16 + Modbus RTU framing |
| `rs485.py` | UART + DE pin driver, wraps `modbus_rtu` |
| `level_sensor.py` | Register decode + unit conversion (bar / °C) |
| `frames.py` | Builds `readings` / `status` / `command/ack` JSON |
| `frame_buffer.py` | Bounded flash file with oldest-first trimming |
| `commands.py` | Command dispatch with per-command-id deduplication |
| `mqtt_client.py` | Self-contained MQTT 3.1.1 client (TLS + QoS 1) |
| `wifi.py` | WiFi STA connect + check |
| `nettime.py` | NTP sync + ISO-8601 UTC timestamp |
| `backfill.py` | Optional HTTPS batch fallback to `/api/v1/ingest/backfill` |
| `device.py` | MAC, uptime, RSSI, watchdog, reboot |