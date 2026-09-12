import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from frames import build_ack, build_reading, build_status


class BuildReadingTest(unittest.TestCase):
    def test_full(self):
        frame = build_reading("AA:BB:CC:DD:EE:01", "SS-010203040506",
                              0.7362, temperature_c=24.5, status=0,
                              timestamp="2026-09-12T14:00:00Z")
        self.assertEqual(frame["gateway_mac"], "AA:BB:CC:DD:EE:01")
        self.assertEqual(frame["sensor_serial_number"], "SS-010203040506")
        self.assertEqual(frame["measurement"]["pressure"], 0.7362)
        self.assertEqual(frame["measurement"]["temperature"], 24.5)
        self.assertEqual(frame["measurement"]["status"], 0)
        self.assertEqual(frame["measurement"]["timestamp"], "2026-09-12T14:00:00Z")

    def test_omits_none_temperature_and_timestamp(self):
        frame = build_reading("AA:BB:CC:DD:EE:01", "SS-1", 0.5)
        self.assertEqual(frame["gateway_mac"], "AA:BB:CC:DD:EE:01")
        self.assertNotIn("temperature", frame["measurement"])
        self.assertNotIn("timestamp", frame["measurement"])

    def test_pressure_mandatory(self):
        with self.assertRaises(ValueError):
            build_reading("AA:BB:CC:DD:EE:01", "SS-1", None)


class BuildStatusTest(unittest.TestCase):
    def test_defaults(self):
        frame = build_status("AA:BB:CC:DD:EE:01", "1.0.0")
        self.assertEqual(frame, {
            "status": "online",
            "firmware_version": "1.0.0",
        })

    def test_with_diagnostics(self):
        frame = build_status("AA:BB:CC:DD:EE:01", "1.0.0", uptime_s=3600,
                             rssi=-55, reset_cause="power_on",
                             timestamp="2026-09-12T14:00:00Z")
        self.assertEqual(frame["uptime_s"], 3600)
        self.assertEqual(frame["rssi_dbm"], -55)
        self.assertEqual(frame["reset_cause"], "power_on")


class BuildAckTest(unittest.TestCase):
    def test_executed(self):
        self.assertEqual(
            build_ack("abc-123", "executed", "ping ok"),
            {"command_id": "abc-123", "status": "executed", "detail": "ping ok"},
        )

    def test_rejected_no_detail(self):
        self.assertEqual(
            build_ack("abc-123", "rejected"),
            {"command_id": "abc-123", "status": "rejected"},
        )

    def test_bad_status(self):
        with self.assertRaises(ValueError):
            build_ack("abc-123", "maybe")


if __name__ == "__main__":
    unittest.main()