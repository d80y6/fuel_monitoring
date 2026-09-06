# Fuel Monitoring ESP32-S3 Gateway Firmware

## Build Requirements
- MicroPython 1.22+ for ESP32-S3
- `rshell` or `ampy` for file transfer
- `esptool.py` for flashing

## Flashing
```bash
# Flash MicroPython firmware
esptool.py --port /dev/ttyUSB0 write_flash 0x1000 esp32s3-20230909-v1.22.0.bin

# Deploy application
rshell --port /dev/ttyUSB0 cp firmware/ /flash/

# Run
rshell --port /dev/ttyUSB0 repl -c "import firmware"
```

## Configuration
Edit `main.py` CONFIG dict before flashing:
- `gateway_mac`: Unique MAC address identifier
- `wifi_ssid/wifi_pass`: Network credentials
- `mqtt_broker`: Broker hostname/IP
- `sensors`: List of sensor configurations with serial numbers and RS485 addresses

## Offline Buffer
Readings are buffered in SPIFFS flash (10,000 entries) during network outages.
On reconnection, buffered readings are sent before new readings.

## OTA Updates
Firmware supports OTA updates via `update_firmware` command.
