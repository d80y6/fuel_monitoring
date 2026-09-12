"""Deployment configuration template.

Copy to ``config.py`` on the device and fill in the secrets. ``main.run()``
falls back to safe defaults if ``config`` is missing, but a device without
WiFi credentials is useless, so provision ``config.py`` on first flash.
"""

WIFI_SSID = "replace-me"
WIFI_PASSWORD = "replace-me"

# Sensor / RS-485
MODBUS_SLAVE_ID = 1
MODBUS_BAUDRATE = 9600
MODBUS_UART_ID = 1
MODBUS_TX_PIN = 17
MODBUS_RX_PIN = 16
MODBUS_DE_PIN = 4
MODBUS_POLL_TIMEOUT_S = 0.3
REGISTERS_START = 0
REGISTERS_COUNT = 4

SENSOR = {
    "pressure": {
        "registers": [0, 1],
        "endian": "big",
        "kind": "level_mm",       # level_mm | level_cm | mbar | hpa | bar
        "scale": 1.0,
        "offset": 0.0,
        "density_kg_m3": 750.0,   # gasoline; override per tank
    },
    "temperature": {
        "registers": [2],
        "kind": "c_1e1",          # raw | c_1e1 | c_1e2
        "scale": 1.0,
        "offset": 0.0,
    },
    "status": {"registers": [3], "mask": 0xFFFF},
}

# Identity
GATEWAY_MAC_OVERRIDE = None       # e.g. "AA:BB:CC:DD:EE:01"; None => STA MAC
SENSOR_SERIAL_OVERRIDE = None     # e.g. "SS-010203040506"; None => "SS-<mac>"
FIRMWARE_VERSION = "1.0.0"

# MQTT
MQTT_HOST = "broker.example.com"
MQTT_PORT = 8883
MQTT_USERNAME = "gateway"
MQTT_PASSWORD = "replace-me"
MQTT_TLS = True
MQTT_CA_PATH = "/certs/ca.pem"
MQTT_CERT_PATH = "/certs/client.pem"
MQTT_KEY_PATH = "/certs/client.key"
MQTT_KEEPALIVE_S = 60
MQTT_CONNECT_TIMEOUT_S = 8.0

# Timing
SAMPLE_INTERVAL_S = 60
HEARTBEAT_INTERVAL_S = 300
WATCHDOG_TIMEOUT_S = 30
NTP_HOST = "pool.ntp.org"

# Offline buffering
BUFFER_PATH = "/data/frames.jsonl"
BUFFER_MAX_FRAMES = 2000
BUFFER_MAX_BYTES = 4 * 1024 * 1024
BACKFILL_URL = ""  # e.g. "https://ingestion.example.com" ("" disables HTTPS fallback)

# RS-485 enable the upstream legacy probe read; 0 disables Modbus polling
SENSOR_ENABLED = True