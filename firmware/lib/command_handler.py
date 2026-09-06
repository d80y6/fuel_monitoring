"""Bi-directional command handler for ESP32-S3 gateway."""
import gc
import ujson
import time
import network
import uos
import machine

from lib.keller import KellerReader


class CommandHandler:
    """Handle commands sent from cloud to gateway and vice versa."""

    VALID_COMMANDS = {"get_config", "set_interval", "reboot", "diagnose", "update_firmware"}

    def __init__(self, config, uart_config=None):
        self.config = config
        self.uart_config = uart_config or {}
        self._command_history = []
        self._max_history = 100
        self._sensor_readers = {}

    def _get_reader(self, sensor):
        key = sensor["address"]
        if key not in self._sensor_readers:
            self._sensor_readers[key] = KellerReader(
                address=sensor["address"],
                pressure_channel=sensor["pressure_ch"],
                temp_channel=sensor["temp_ch"],
                uart_id=self.uart_config.get("id", 0),
                tx_pin=self.uart_config.get("tx_pin", 17),
                rx_pin=self.uart_config.get("rx_pin", 16),
                de_pin=self.uart_config.get("de_pin", 4),
                baudrate=self.uart_config.get("baudrate", 9600)
            )
        return self._sensor_readers[key]

    def execute_from_mqtt(self, topic, payload):
        parsed = self.parse_command(topic, ujson.dumps(payload))
        if "error" in parsed:
            return parsed
        return self.execute_command(parsed["command"], parsed.get("params", {}))

    def parse_command(self, topic, payload):
        try:
            data = ujson.loads(payload)
            command = data.get("command")

            if command not in self.VALID_COMMANDS:
                return {"error": "Unknown command: %s" % command}

            self._command_history.append({
                "command": command,
                "topic": topic,
                "timestamp": time.time(),
                "params": data.get("params", {})
            })
            if len(self._command_history) > self._max_history:
                self._command_history = self._command_history[-self._max_history:]

            return {"command": command, "params": data.get("params", {})}
        except Exception as e:
            return {"error": str(e)}

    def execute_command(self, command, params):
        if command == "get_config":
            return self._get_config()
        elif command == "set_interval":
            return self._set_interval(params)
        elif command == "reboot":
            return self._reboot()
        elif command == "diagnose":
            return self._diagnose()
        elif command == "update_firmware":
            return self._update_firmware(params)
        return {"error": "Unknown command: %s" % command}

    def _get_config(self):
        return {
            "gateway_mac": self.config.get("gateway", {}).get("mac", ""),
            "reading_interval": self.config.get("gateway", {}).get("reading_interval", 300),
            "sensor_count": len(self.config.get("sensors", [])),
            "firmware_version": self.config.get("version", "2.0.0"),
            "uptime": time.time(),
            "free_memory": gc.mem_free()
        }

    def _set_interval(self, params):
        interval = params.get("interval", 300)
        if 30 <= interval <= 3600:
            gw = self.config.get("gateway", {})
            gw["reading_interval"] = interval
            return {"status": "success", "interval": interval}
        return {"error": "Interval must be between 30 and 3600 seconds"}

    def _reboot(self):
        gc.collect()
        machine.reset()

    def _diagnose(self):
        sensor_status = []
        for sensor in self.config.get("sensors", []):
            try:
                reader = self._get_reader(sensor)
                reader.read_serial_number()
                sensor_status.append({
                    "serial_number": sensor["serial_number"],
                    "status": "online"
                })
            except Exception:
                sensor_status.append({
                    "serial_number": sensor["serial_number"],
                    "status": "offline"
                })

        return {
            "wifi_strength": self._get_wifi_strength(),
            "free_memory": gc.mem_free(),
            "buffer_size": len(self._command_history),
            "uptime": time.time(),
            "sensor_status": sensor_status,
            "mqtt_connected": True,
            "flash_used": self._get_flash_usage()
        }

    def _update_firmware(self, params):
        version = params.get("version")
        url = params.get("url")
        if not version or not url:
            return {"error": "version and url are required"}

        ota_config = self.config.get("ota", {})
        max_retries = ota_config.get("max_retries", 3)

        try:
            import urequests
            for attempt in range(max_retries):
                try:
                    resp = urequests.get(url, timeout=60)
                    if resp.status_code == 200:
                        import uhashlib
                        firmware_data = resp.content
                        resp.close()

                        import esp
                        esp.flash_os_ui_set(0)
                        flash_size = len(firmware_data)
                        esp.flash_write(0x10000, firmware_data, flash_size)

                        return {"status": "success", "version": version, "size": flash_size}
                    resp.close()
                except Exception:
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
            return {"error": "OTA update failed after %d attempts" % max_retries}
        except ImportError:
            return {"error": "urequests not available for OTA"}

    def _get_wifi_strength(self):
        try:
            sta = network.WLAN(network.STA_IF)
            return sta.status("rssi")
        except Exception:
            return -1

    def _get_flash_usage(self):
        try:
            stat = uos.statvfs('/')
            total = stat[0] * stat[1]
            free = stat[0] * stat[2]
            return {"total": total, "used": total - free, "free": free}
        except Exception:
            return {}

    def close_readers(self):
        for reader in self._sensor_readers.values():
            try:
                reader.close()
            except Exception:
                pass
        self._sensor_readers.clear()
