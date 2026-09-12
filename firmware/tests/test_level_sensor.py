import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from level_sensor import decode_registers, pressure_bar_from_raw, temperature_c_from_raw

G = 9.80665


class PressureTest(unittest.TestCase):
    def test_level_mm_default_density(self):
        # 750 mm column of 750 kg/m3 gasoline.
        bar = pressure_bar_from_raw(750, {"kind": "level_mm", "density_kg_m3": 750.0})
        self.assertAlmostEqual(bar, 0.750 * 750.0 * G / 100000.0, places=6)
        self.assertAlmostEqual(bar, 0.055162375, places=6)

    def test_level_mm_custom_density(self):
        bar = pressure_bar_from_raw(1000, {"kind": "level_mm", "density_kg_m3": 840.0})
        self.assertAlmostEqual(bar, 1.000 * 840.0 * G / 100000.0, places=6)

    def test_mbar(self):
        self.assertAlmostEqual(pressure_bar_from_raw(736.2, {"kind": "mbar"}), 0.7362)

    def test_bar(self):
        self.assertAlmostEqual(pressure_bar_from_raw(1.02, {"kind": "bar"}), 1.02)

    def test_scale_offset(self):
        self.assertAlmostEqual(
            pressure_bar_from_raw(500, {"kind": "mbar", "scale": 10.0, "offset": 5.0}),
            5.005,
        )

    def test_unknown_kind(self):
        with self.assertRaises(ValueError):
            pressure_bar_from_raw(10, {"kind": "furlongs"})


class TemperatureTest(unittest.TestCase):
    def test_raw(self):
        self.assertEqual(temperature_c_from_raw(24.5, {"kind": "raw"}), 24.5)

    def test_c_1e1(self):
        self.assertEqual(temperature_c_from_raw(245, {"kind": "c_1e1"}), 24.5)

    def test_c_1e2(self):
        self.assertEqual(temperature_c_from_raw(2450, {"kind": "c_1e2"}), 24.5)

    def test_unknown_kind(self):
        with self.assertRaises(ValueError):
            temperature_c_from_raw(1, {"kind": "parsecs"})


class DecodeRegistersTest(unittest.TestCase):
    CFG = {
        "pressure": {"registers": [0, 1], "kind": "level_mm", "density_kg_m3": 750.0},
        "temperature": {"registers": [2], "kind": "c_1e1"},
        "status": {"registers": [3], "mask": 0x000F},
    }

    def test_full_decode(self):
        # reg0/1 = 750 mm u32, reg2 = 245 (=24.5 °C), reg3 = 3.
        value = 750
        read = decode_registers([value >> 16, value & 0xFFFF, 245, 3], self.CFG)
        self.assertAlmostEqual(read.pressure_bar, 0.750 * 750.0 * G / 100000.0, places=6)
        self.assertAlmostEqual(read.temperature_c, 24.5)
        self.assertEqual(read.status, 3)
        self.assertEqual(read.errors, ())

    def test_status_mask(self):
        read = decode_registers([0, 1, 245, 0x11], self.CFG)
        self.assertEqual(read.status, 0x01)

    def test_status_register_out_of_range(self):
        read = decode_registers([0, 0, 245], self.CFG)
        self.assertEqual(read.status, 0)
        self.assertIsNotNone(read.pressure_bar)

    def test_error_accumulated(self):
        cfg = {"pressure": {"registers": [0], "kind": "furlongs"}}
        read = decode_registers([10], cfg)
        self.assertIsNone(read.pressure_bar)
        self.assertEqual(len(read.errors), 1)
        self.assertIn("pressure", read.errors[0])


if __name__ == "__main__":
    unittest.main()