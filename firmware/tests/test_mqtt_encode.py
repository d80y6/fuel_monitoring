import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mqtt_client import _encode_remaining_length, _encode_utf8


class RemainingLengthTest(unittest.TestCase):
    def test_single_byte(self):
        self.assertEqual(_encode_remaining_length(0), b"\x00")
        self.assertEqual(_encode_remaining_length(127), b"\x7f")

    def test_two_byte_boundary(self):
        self.assertEqual(_encode_remaining_length(128), b"\x80\x01")
        self.assertEqual(_encode_remaining_length(16383), b"\xff\x7f")

    def test_three_byte_boundary(self):
        self.assertEqual(_encode_remaining_length(16384), b"\x80\x80\x01")
        self.assertEqual(_encode_remaining_length(2048), b"\x80\x10")


class Utf8Test(unittest.TestCase):
    def test_utf8(self):
        self.assertEqual(_encode_utf8("MQTT"), b"\x00\x04MQTT")
        self.assertEqual(_encode_utf8(""),
                         b"\x00\x00")
        encoded = "caf\x00e9".encode("utf-8")
        self.assertEqual(_encode_utf8("caf\x00e9"), b"\x00\x06" + encoded)


if __name__ == "__main__":
    unittest.main()