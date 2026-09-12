"""Modbus-RTU master framing: CRC-16/Modbus, request/response codecs.

Pure functions only — no hardware imports — so the wire protocol is unit-testable
on the host. The RS-485 I/O lives in ``rs485.py``.
"""

_FUNC_READ_HOLDING = 0x03
_FUNC_WRITE_SINGLE = 0x06


class ModbusError(ValueError):
    """Raised for slave exception responses or malformed frames."""

    EXCEPTION_CODES = {
        1: "illegal function",
        2: "illegal data address",
        3: "illegal data value",
        4: "slave device failure",
    }


def crc16(data: bytes) -> int:
    """CRC-16/Modbus (poly 0xA001 reflected)."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def frame_with_crc(frame: bytes) -> bytes:
    crc = crc16(frame)
    return frame + bytes((crc & 0xFF, crc >> 8))


def build_read_holding_registers(slave: int, start_reg: int, count: int) -> bytes:
    if not (0 <= slave <= 0xFF):
        raise ValueError("slave address out of range")
    if not (0 <= count <= 0x7D):
        raise ValueError("register count out of range")
    return frame_with_crc(
        bytes((slave, _FUNC_READ_HOLDING, start_reg >> 8, start_reg & 0xFF,
               count >> 8, count & 0xFF))
    )


def build_write_single_register(slave: int, reg: int, value: int) -> bytes:
    return frame_with_crc(
        bytes((slave, _FUNC_WRITE_SINGLE, reg >> 8, reg & 0xFF,
               value >> 8, value & 0xFF))
    )


def parse_response(frame: bytes, expected_slave: int, expected_count: int) -> list[int]:
    """Parse a read-holding-registers response into raw 16-bit values."""
    if frame is None or len(frame) < 5:
        raise ModbusError("short frame")
    if frame[0] != expected_slave:
        raise ModbusError("slave address mismatch")
    func = frame[1]
    if func & 0x80:
        code = frame[2]
        raise ModbusError(
            "slave exception %d: %s" % (code, ModbusError.EXCEPTION_CODES.get(code, "unknown"))
        )
    if func != _FUNC_READ_HOLDING:
        raise ModbusError("unexpected function code 0x%02X" % func)
    expected_len = 3 + expected_count * 2 + 2
    if len(frame) != expected_len:
        raise ModbusError("length mismatch: got %d, want %d" % (len(frame), expected_len))
    if frame[2] != expected_count * 2:
        raise ModbusError("byte count mismatch: %d" % frame[2])
    if crc16(frame[:-2]) != (frame[-2] | (frame[-1] << 8)):
        raise ModbusError("CRC mismatch")
    values = []
    for i in range(expected_count):
        hi, lo = frame[3 + i * 2], frame[4 + i * 2]
        values.append((hi << 8) | lo)
    return values


def assemble_u32(values: list[int], endian: str = "big") -> int:
    """Combine two register values into one 32-bit unsigned integer."""
    if endian == "big":
        return ((values[0] << 16) | values[1]) & 0xFFFFFFFF
    if endian == "little":
        return ((values[1] << 16) | values[0]) & 0xFFFFFFFF
    raise ValueError("endian must be 'big' or 'little'")