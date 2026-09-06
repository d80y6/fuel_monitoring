"""ESP32-S3 MicroPython Gateway Application for Fuel Monitoring."""
import gc
import time
import ujson
import machine
import network

from lib.keller import KellerReader
from lib.mqtt_client import MQTTClient
from lib.buffer import OfflineBuffer
from lib.command_handler import CommandHandler


def load_config():
    try:
        with open('/firmware/firmware.json', 'r') as f:
            return ujson.load(f)
    except (OSError, ValueError):
        return {}


CONFIG = load_config()

gc.collect()

sta = network.WLAN(network.STA_IF)
sta.active(True)

buffer = OfflineBuffer(
    max_size=CONFIG.get("gateway", {}).get("max_buffered", 10000),
    filepath=CONFIG.get("gateway", {}).get("buffer_file", "/buffer/readings.json"),
    flush_interval=10
)

command_handler = CommandHandler(CONFIG, uart_config=CONFIG.get("uart", {}))

mqtt = MQTTClient(
    client_id="gateway_%s" % CONFIG.get("gateway", {}).get("mac", "000000").replace(":", "")[-6:],
    server=CONFIG.get("mqtt", {}).get("broker", ""),
    port=CONFIG.get("mqtt", {}).get("port", 8883),
    ssl=CONFIG.get("mqtt", {}).get("ssl", True),
    keepalive=CONFIG.get("mqtt", {}).get("keepalive", 60),
    max_reconnect_delay=CONFIG.get("mqtt", {}).get("max_reconnect_delay", 300),
    topic_prefix=CONFIG.get("mqtt", {}).get("topic_prefix", "fuel"),
    max_buffered=50
)
mqtt.set_command_handler(command_handler)

reader_cache = {}

WIFI_BACKOFF_MAX = CONFIG.get("wifi", {}).get("backoff_max", 300)


def get_reader(sensor):
    addr = sensor["address"]
    if addr not in reader_cache:
        uart_cfg = CONFIG.get("uart", {})
        reader_cache[addr] = KellerReader(
            address=sensor["address"],
            pressure_channel=sensor["pressure_ch"],
            temp_channel=sensor["temp_ch"],
            uart_id=uart_cfg.get("id", 0),
            tx_pin=uart_cfg.get("tx_pin", 17),
            rx_pin=uart_cfg.get("rx_pin", 16),
            de_pin=uart_cfg.get("de_pin", 4),
            baudrate=uart_cfg.get("baudrate", 9600)
        )
    return reader_cache[addr]


def check_wifi():
    if sta.isconnected():
        return True

    wifi_cfg = CONFIG.get("wifi", {})
    ssid = wifi_cfg.get("ssid", "")
    password = wifi_cfg.get("pass", "")
    max_retries = wifi_cfg.get("max_retries", 10)
    backoff_base = wifi_cfg.get("backoff_base", 2)

    sta.connect(ssid, password)
    delay = 1
    for attempt in range(max_retries):
        if sta.isconnected():
            return True
        time.sleep(min(delay, WIFI_BACKOFF_MAX))
        delay *= backoff_base

    sta.disconnect()
    return False


def mqtt_connected():
    if not mqtt.is_connected():
        try:
            mqtt.reconnect()
            mqtt.drain_buffer()
        except Exception:
            return False
    return mqtt.is_connected()


def publish_readings(payload):
    gc.collect()
    topic_prefix = CONFIG.get("mqtt", {}).get("topic_prefix", "fuel")
    client_id = mqtt.client_id
    topic = "%s/%s/readings" % (topic_prefix, client_id)
    mqtt.publish(topic, payload, qos=1)
    mqtt.loop()


def build_payload(readings):
    gw_mac = CONFIG.get("gateway", {}).get("mac", "00:00:00:00:00:00")
    return ujson.dumps({
        "gateway_mac": gw_mac,
        "timestamp": int(time.time()),
        "sensors": readings
    })


def read_all_sensors():
    readings = []
    for sensor in CONFIG.get("sensors", []):
        try:
            reader = get_reader(sensor)
            pressure = reader.read_pressure()
            temperature = reader.read_temperature()
            readings.append({
                "serial_number": sensor["serial_number"],
                "pressure_bar": pressure,
                "temperature_c": temperature,
                "status": 0,
                "timestamp": int(time.time())
            })
        except Exception as e:
            readings.append({
                "serial_number": sensor["serial_number"],
                "status": 1,
                "timestamp": int(time.time()),
                "error": str(e)
            })
    return readings


def drain_buffer():
    buffered = buffer.drain()
    if buffered:
        gc.collect()
        payload = build_payload(buffered)
        publish_readings(payload)


def cleanup():
    for reader in reader_cache.values():
        try:
            reader.close()
        except Exception:
            pass
    reader_cache.clear()
    try:
        mqtt.disconnect()
    except Exception:
        pass


def main():
    wdt_timeout = CONFIG.get("watchdog", {}).get("timeout_ms", 30000)
    wdt = machine.WDT(timeout=wdt_timeout)

    reading_interval = CONFIG.get("gateway", {}).get("reading_interval", 300)

    try:
        while True:
            try:
                wdt.feed()
                gc.collect()

                readings = []

                if not check_wifi():
                    time.sleep(5)
                    continue

                readings = read_all_sensors()

                if mqtt_connected():
                    mqtt.loop()
                    gc.collect()
                    payload = build_payload(readings)
                    publish_readings(payload)
                    drain_buffer()
                else:
                    buffer.add(readings)

                buffer.flush()

                if mqtt.should_reset():
                    gc.collect()
                    machine.reset()

                mqtt.loop()
                time.sleep(reading_interval)

            except KeyboardInterrupt:
                break
            except Exception as e:
                buffer.add(readings)
                time.sleep(10)
                gc.collect()
    finally:
        cleanup()


if __name__ == "__main__":
    main()
