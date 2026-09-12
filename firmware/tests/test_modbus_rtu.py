import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest

from modbus_rtu import (
    ModbusError,
    assemble_u32,
    build_read_holding_registers,
    build_write_single_register,
    crc16,
    parse_response,
)


class Crc16Test(unittest.TestCase):
    def test_known_vector(self):
        # Frame {01 03 00 00 00 0A} carries CRC bytes C5 CD (lo-then-hi).
        frame = bytes.fromhex("01030000000a")
        crc = crc16(frame)
        self.assertEqual(frame + bytes((crc & 0xFF, crc >> 8)),
                         bytes.fromhex("01030000000ac5cd"))

    def test_write_vector_roundtrip(self):
        frame = build_write_single_register(1, 0x0008, 0x0258)
        self.assertEqual(crc16(frame[:-2]), frame[-2] | (frame[-1] << 8))
        self.assertEqual(bytes(frame[:6]), bytes.fromhex("010600080258"))


class ReadRequestTest(unittest.TestCase):
    def test_read_vector(self):
        frame = build_read_holding_registers(1, 0, 10)
        self.assertEqual(bytes(frame), bytes.fromhex("01030000000ac5cd"))

    def test_read_nonzero_start(self):
        frame = build_read_holding_registers(2, 0x010B, 3)
        self.assertEqual(crc16(frame[:-2]), frame[-2] | (frame[-1] << 8))
        self.assertEqual(frame[0], 2)
        self.assertEqual(frame[2:4], bytes((0x01, 0x0B)))

    def test_count_bounds(self):
        with self.assertRaises(ValueError):
            build_read_holding_registers(1, 0, 0x7E)


class ParseResponseTest(unittest.TestCase):
    def _response(self, body):
        frame = bytes(body)
        crc = crc16(frame)
        return frame + bytes((crc & 0xFF, crc >> 8))

    def test_two_registers(self):
        raw = self._response([0x01, 0x03, 0x04, 0x00, 0x1F, 0x04, 0x02])
        self.assertEqual(parse_response(raw, 1, 2), [31, 1026])

    def test_slave_mismatch(self):
        raw = self._response([0x02, 0x03, 0x02, 0x00, 0x10])
        with self.assertRaises(ModbusError):
            parse_response(raw, 1, 1)

    def test_exception_frame(self):
        raw = self._response([0x01, 0x83, 0x02])
        with self.assertRaises(ModbusError) as ctx:
            parse_response(raw, 1, 1)
        self.assertIn("illegal data address", str(ctx.exception))

    def test_crc_bad(self):
        raw = self._response([0x01, 0x03, 0x02, 0x00, 0x10])
        bad = raw[:-2] + bytes((raw[-2] ^ 0xFF, raw[-1]))
        with self.assertRaises(ModbusError):
            parse_response(bad, 1, 1)

    def test_length_mismatch(self):
        raw = self._response([0x01, 0x03, 0x02, 0x00, 0x10])
        with self.assertRaises(ModbusError):
            parse_response(raw, 1, 5)


class AssembleU32Test(unittest.TestCase):
    def test_big(self):
        self.assertEqual(assemble_u32([0x1234, 0x5678], "big"), 0x12345678)

    def test_little(self):
        self.assertEqual(assemble_u32([0x1234, 0x5678], "little"), 0x56781234)


if __name__ == "__main__":
    unittest.main()