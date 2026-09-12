import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands import CommandRegistry


class FakeClock:
    def __init__(self):
        self.value = 1_000_000

    def now(self):
        return self.value


class CommandRegistryTest(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.registry = CommandRegistry(now=self.clock.now)

    def test_ping(self):
        ack, effect = self.registry.handle(
            {"command_id": "1", "type": "ping", "payload": {}})
        self.assertEqual(ack["status"], "executed")
        self.assertEqual(ack["command_id"], "1")
        self.assertIsNone(effect)

    def test_set_interval(self):
        ack, effect = self.registry.handle(
            {"command_id": "2", "type": "set_interval", "payload": {"seconds": 30}})
        self.assertEqual(ack["status"], "executed")
        self.assertEqual(effect, {"action": "set_interval", "seconds": 30})

    def test_set_interval_clamps_high(self):
        _, effect = self.registry.handle(
            {"command_id": "3", "type": "set_interval", "payload": {"seconds": 999999}})
        self.assertEqual(effect["seconds"], 3600)

    def test_set_interval_clamps_low(self):
        _, effect = self.registry.handle(
            {"command_id": "4", "type": "set_interval", "payload": {"seconds": 1}})
        self.assertEqual(effect["seconds"], 5)

    def test_set_interval_rejects_non_numeric(self):
        ack, effect = self.registry.handle(
            {"command_id": "5", "type": "set_interval", "payload": {"seconds": "abc"}})
        self.assertEqual(ack["status"], "rejected")
        self.assertIn("invalid", ack["detail"])
        self.assertIsNone(effect)

    def test_status_probe(self):
        ack, effect = self.registry.handle(
            {"command_id": "6", "type": "status_probe", "payload": {}})
        self.assertEqual(effect, {"action": "status_probe"})

    def test_reboot(self):
        ack, effect = self.registry.handle(
            {"command_id": "7", "type": "reboot", "payload": {}})
        self.assertEqual(effect, {"action": "reboot"})

    def test_unknown_type_rejected(self):
        ack, effect = self.registry.handle(
            {"command_id": "8", "type": "flash_led", "payload": {}})
        self.assertEqual(ack["status"], "rejected")
        self.assertIn("flash_led", ack["detail"])
        self.assertIsNone(effect)

    def test_duplicate_is_idempotent(self):
        command = {"command_id": "9", "type": "set_interval", "payload": {"seconds": 60}}
        ack1, effect1 = self.registry.handle(command)
        ack2, effect2 = self.registry.handle(command)
        self.assertEqual(ack1["status"], "executed")
        self.assertIsNotNone(effect1)
        self.assertEqual(ack2["detail"], "duplicate")
        self.assertIsNone(effect2)

    def test_missing_fields_not_ackable(self):
        self.assertEqual(self.registry.handle({"type": "ping"}), (None, None))
        self.assertEqual(self.registry.handle({"command_id": "10"}), (None, None))

    def test_expired_duplicate_replays_effect(self):
        command = {"command_id": "11", "type": "reboot", "payload": {}}
        _, effect1 = self.registry.handle(command)
        self.assertIsNotNone(effect1)
        self.clock.value += 25 * 3600
        self.registry.handle({"command_id": "12", "type": "ping", "payload": {}})
        _, effect2 = self.registry.handle(command)
        self.assertIsNotNone(effect2)


if __name__ == "__main__":
    unittest.main()