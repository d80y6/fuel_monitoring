"""Keller protocol RS485 communication for ESP32-S3."""
import machine
import struct
import time


class KellerReader:
    """Read pressure/temperature from Keller sensors via RS485."""

    INITIALIZE = 0x30
    READ_CHANNEL_FLOAT = 0x49
    READ_SERIAL_NUMBER = 0x5F

    def __init__(self, address, pressure_channel, temp_channel,
                 uart_id=0, tx_pin=17, rx_pin=16, de_pin=4, baudrate=9600):
        self.address = address
        self.pressure_channel = pressure_channel
        self.temp_channel = temp_channel

        self.uart = machine.UART(
            uart_id,
            baudrate=baudrate,
            bits=8,
            parity=None,
            stop=1,
            timeout=5000,
            tx=machine.Pin(tx_pin),
            rx=machine.Pin(rx_pin)
        )

        self.de_pin = machine.Pin(de_pin, machine.Pin.OUT)
        self.de_pin.off()

    def _crc16(self, data):
        """Calculate CRC-16 for Keller/MODBUS polynomial."""
        crc = 0xFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x0001:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1
        return crc

    def _expected_response_length(self, function):
        """Return expected response length based on function code."""
        if function == self.READ_CHANNEL_FLOAT:
            return 12
        elif function == self.READ_SERIAL_NUMBER:
            return 10
        elif function == self.INITIALIZE:
            return 6
        return 12

    def _send_request(self, function, data=None):
        """Send RS485 request and receive response with CRC validation."""
        request = bytearray([self.address, function])
        if data is not None:
            request.append(data)

        crc = self._crc16(bytes(request))
        request.append((crc >> 8) & 0xFF)
        request.append(crc & 0xFF)

        self.de_pin.on()
        self.uart.write(bytes(request))

        tx_time = time.ticks_ms()
        expected_len = self._expected_response_length(function)
        byte_time_ms = max(2, (expected_len * 10 * 1000) // 9600 + 10)

        while time.ticks_diff(time.ticks_ms(), tx_time) < byte_time_ms:
            if self.uart.any():
                break
            time.sleep_ms(2)

        self.de_pin.off()

        buf = bytearray()
        start = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start) < 100:
            if len(buf) >= expected_len:
                break
            n = self.uart.any()
            if n:
                chunk = self.uart.read(min(n, expected_len - len(buf)))
                if chunk:
                    buf.extend(chunk)
            time.sleep_ms(2)

        if len(buf) < 5:
            return None

        if not self._validate_crc(bytes(buf)):
            return None

        return bytes(buf)

    def _validate_crc(self, response):
        """Validate response CRC using spec-compliant byte order."""
        if len(response) < 5:
            return False
        data = response[:-2]
        received_crc = (response[-2] << 8) | response[-1]
        calculated = self._crc16(data)
        return received_crc == calculated

    def read_pressure(self):
        """Read pressure from pressure channel."""
        response = self._send_request(self.READ_CHANNEL_FLOAT, self.pressure_channel)
        if not response or len(response) < 9:
            raise ConnectionError("No valid pressure response from sensor %d" % self.address)

        value = struct.unpack('>f', bytes(response[2:6]))[0]
        status = (response[6] << 8) | response[7]
        if status != 0:
            raise ConnectionError("Sensor %d status error: 0x%04X" % (self.address, status))

        return round(value, 5)

    def read_temperature(self):
        """Read temperature from temperature channel."""
        response = self._send_request(self.READ_CHANNEL_FLOAT, self.temp_channel)
        if not response or len(response) < 9:
            raise ConnectionError("No valid temperature response from sensor %d" % self.address)

        value = struct.unpack('>f', bytes(response[2:6]))[0]
        return round(value, 1)

    def read_serial_number(self):
        """Read sensor serial number."""
        response = self._send_request(self.READ_SERIAL_NUMBER)
        if not response or len(response) < 8:
            raise ConnectionError("No valid serial number response from sensor %d" % self.address)

        serial = (response[2] << 24) | (response[3] << 16) | (response[4] << 8) | response[5]
        return serial

    def initialize(self):
        """Initialize the K114 converter."""
        response = self._send_request(self.INITIALIZE)
        if response and response[1] == self.INITIALIZE:
            time.sleep_ms(3000)
            return True
        raise ConnectionError("Initialization failed for sensor %d" % self.address)

    def close(self):
        """Deinitialize UART and set DE low."""
        self.uart.deinit()
        self.de_pin.off()
