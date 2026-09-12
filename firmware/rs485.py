"""RS-485 (half-duplex) transport for the Modbus-RTU master.

Drive ``DE``/``RE`` high to transmit, low to receive. Pure framing lives in
``modbus_rtu``; this module owns the UART I/O and timing only.
"""

from machine import Pin, UART
import time

from modbus_rtu import build_read_holding_registers, parse_response


class Rs485Bus:
    def __init__(self, uart_id: int, tx_pin: int, rx_pin: int, de_pin: int,
                 baudrate: int = 9600, timeout_s: float = 0.3):
        self.uart = UART(uart_id, baudrate=baudrate, tx=tx_pin, rx=rx_pin)
        self.de = Pin(de_pin, Pin.OUT, value=0)
        self.timeout_s = timeout_s

    def read_holding_registers(self, slave: int, start_reg: int, count: int) -> list[int]:
        request = build_read_holding_registers(slave, start_reg, count)
        expected = 3 + count * 2 + 2
        self.de.on()
        self.uart.write(request)
        self.de.off()
        getattr(self.uart, "flush", lambda: None)()

        deadline = time.ticks_add(time.ticks_ms(), int(self.timeout_s * 1000))
        buffer = bytearray()
        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            if self.uart.any():
                chunk = self.uart.read(self.uart.any())
                if chunk:
                    buffer.extend(chunk)
                    if len(buffer) >= expected:
                        break
            time.sleep_ms(2)
        return parse_response(bytes(buffer), slave, count)