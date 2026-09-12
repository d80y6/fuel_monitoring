"""Edge gateway entrypoint.

Duty cycle per iteration:
  1. feed watchdog + ensure WiFi
  2. poll the level sensor over RS-485 Modbus-RTU (converting to bar / °C)
  3. publish the reading over MQTT, or buffer it while offline
  4. drain inbound commands (idempotent, acked on ``fuel/<mac>/command/ack``)
  5. publish periodic status heartbeats
On an MQTT (re)connect: publish status, replay the offline buffer, clear it.
"""

import gc
import json
import time

try:
    import config
except ImportError:
    config = None

from backfill import post_frames
from commands import CommandRegistry
from device import Watchdog, mac_address, reboot, rssi_dbm
from frames import build_reading, build_status
from frame_buffer import FrameBuffer
from level_sensor import decode_registers
from mqtt_client import EdgeMqttClient, MqttError
from nettime import iso_utc, sync as sync_time
from rs485 import Rs485Bus
from wifi import ensure_wifi, is_connected


def _cfg(name, default):
    return getattr(config, name, default) if config is not None else default


def _resolve_identity():
    mac = _cfg("GATEWAY_MAC_OVERRIDE", None) or mac_address()
    serial = _cfg("SENSOR_SERIAL_OVERRIDE", None) or ("SS-" + "".join(mac.split(":")))
    return mac, serial


def _build_mqtt(cfg, mac):
    return EdgeMqttClient(
        cfg["host"],
        cfg["port"],
        client_id=("esp32-" + mac.replace(":", "")).encode("utf-8"),
        username=_cfg("MQTT_USERNAME", None),
        password=_cfg("MQTT_PASSWORD", None),
        keepalive=_cfg("MQTT_KEEPALIVE_S", 60),
        command_topic="fuel/%s/command" % mac,
        tls=cfg["tls"],
        ca_path=_cfg("MQTT_CA_PATH", None),
        cert_path=_cfg("MQTT_CERT_PATH", None),
        key_path=_cfg("MQTT_KEY_PATH", None),
        connect_timeout_s=_cfg("MQTT_CONNECT_TIMEOUT_S", 8.0),
    )


def _sample(bus, sensor_cfg, slave, start, count):
    regs = bus.read_holding_registers(slave, start, count)
    return decode_registers(regs, sensor_cfg)


def _sleep_wdt(watchdog, seconds, chunk_s=4):
    watchdog.feed()
    while seconds > 0:
        step = min(seconds, chunk_s)
        time.sleep_ms(int(step * 1000))
        seconds -= step
        watchdog.feed()


def run():
    mac, sensor_serial = _resolve_identity()
    version = _cfg("FIRMWARE_VERSION", "1.0.0")
    firmware_cfg = {
        "host": _cfg("MQTT_HOST", "127.0.0.1"),
        "port": _cfg("MQTT_PORT", 8883),
        "tls": _cfg("MQTT_TLS", True),
    }
    watchdog = Watchdog(_cfg("WATCHDOG_TIMEOUT_S", 30))
    buffer = FrameBuffer(
        _cfg("BUFFER_PATH", "/data/frames.jsonl"),
        max_frames=_cfg("BUFFER_MAX_FRAMES", 2000),
        max_bytes=_cfg("BUFFER_MAX_BYTES", 4 * 1024 * 1024),
    )
    registry = CommandRegistry()
    pending_effect = {}

    bus = None
    sensor_cfg = _cfg("SENSOR", {})
    if _cfg("SENSOR_ENABLED", True) and sensor_cfg:
        bus = Rs485Bus(
            _cfg("MODBUS_UART_ID", 1),
            _cfg("MODBUS_TX_PIN", 17),
            _cfg("MODBUS_RX_PIN", 16),
            _cfg("MODBUS_DE_PIN", 4),
            baudrate=_cfg("MODBUS_BAUDRATE", 9600),
            timeout_s=_cfg("MODBUS_POLL_TIMEOUT_S", 0.3),
        )

    mqtt = _build_mqtt(firmware_cfg, mac)

    def on_command(topic, raw):
        nonlocal pending_effect
        try:
            command = json.loads(raw)
        except ValueError:
            return
        ack, effect = registry.handle(command)
        if ack is None:
            return
        try:
            mqtt.publish("fuel/%s/command/ack" % mac, ack)
        except (MqttError, OSError):
            return
        if effect is not None:
            pending_effect = effect

    mqtt.set_callback(on_command)

    sync_time(_cfg("NTP_HOST", "pool.ntp.org"))
    sample_interval_s = _cfg("SAMPLE_INTERVAL_S", 60)
    heartbeat_interval_s = _cfg("HEARTBEAT_INTERVAL_S", 300)
    started_s = time.monotonic()
    last_heartbeat_s = 0.0
    reconnect_backoff_s = 5.0
    last_backfill_s = 0.0
    mqtt_was_connected = False

    while True:
        gc.collect()
        watchdog.feed()

        if not is_connected():
            ensure_wifi(_cfg("WIFI_SSID", ""), _cfg("WIFI_PASSWORD", ""),
                        timeout_s=15.0)

        pressure = None
        temperature = None
        status_bit = 0
        if bus is not None:
            try:
                read = _sample(bus, sensor_cfg, _cfg("MODBUS_SLAVE_ID", 1),
                               _cfg("REGISTERS_START", 0), _cfg("REGISTERS_COUNT", 4))
                pressure = read.pressure_bar
                temperature = read.temperature_c
                status_bit = read.status
            except (OSError, ValueError):
                status_bit = 0

        now = iso_utc()
        uptime = int(time.monotonic() - started_s)
        frame = None
        if pressure is not None:
            frame = build_reading(mac, sensor_serial, pressure,
                                  temperature_c=temperature,
                                  status=status_bit, timestamp=now)

        if mqtt.connected:
            if not mqtt_was_connected:
                _publish_status(mqtt, mac, version, uptime, now)
                for bf in buffer.snapshot():
                    try:
                        mqtt.publish("fuel/%s/readings" % mac, bf)
                    except (MqttError, OSError):
                        break
                else:
                    buffer.clear()
                last_heartbeat_s = time.monotonic()
                last_backfill_s = time.monotonic()
                reconnect_backoff_s = 5.0

            try:
                if time.monotonic() - last_heartbeat_s >= heartbeat_interval_s:
                    _publish_status(mqtt, mac, version, uptime, iso_utc())
                    last_heartbeat_s = time.monotonic()

                if frame is not None:
                    mqtt.publish("fuel/%s/readings" % mac, frame)
                if mqtt.idle_for_s() >= _cfg("MQTT_KEEPALIVE_S", 60) / 2:
                    mqtt.ping()
                mqtt.poll(timeout_ms=5)

                if pending_effect:
                    effect, pending_effect = pending_effect, {}
                    action = effect.get("action")
                    if action == "set_interval":
                        sample_interval_s = effect["seconds"]
                    elif action == "status_probe":
                        _publish_status(mqtt, mac, version, uptime, iso_utc())
                    elif action == "reboot":
                        mqtt.disconnect()
                        time.sleep_ms(100)
                        reboot()
            except (MqttError, OSError) as exc:
                print("[edge] mqtt error: %s" % exc)
                mqtt.disconnect()

            mqtt_was_connected = True
        else:
            mqtt_was_connected = False
            if frame is not None:
                buffer.append(frame)
            if _cfg("BACKFILL_URL", ""):
                frames = buffer.snapshot()
                if frames and time.monotonic() - last_backfill_s >= 300:
                    last_backfill_s = time.monotonic()
                    post_frames(frames, _cfg("BACKFILL_URL"))
            watchdog.feed()
            try:
                mqtt.connect()
                reconnect_backoff_s = 5.0
            except (MqttError, OSError) as exc:
                print("[edge] mqtt connect failed: %s" % exc)
                _sleep_wdt(watchdog, reconnect_backoff_s)
                reconnect_backoff_s = min(reconnect_backoff_s * 2, 60.0)
            continue

        watchdog.feed()
        _sleep_wdt(watchdog, sample_interval_s)


def _publish_status(mqtt, mac, version, uptime_s, timestamp):
    mqtt.publish("fuel/%s/status" % mac, build_status(
        mac, version, uptime_s=uptime_s, rssi=rssi_dbm(), timestamp=timestamp))


if __name__ == "__main__":
    run()