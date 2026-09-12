import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from frame_buffer import FrameBuffer


class FrameBufferTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "frames.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def _make(self, max_frames=100, max_bytes=1 << 20):
        return FrameBuffer(self.path, max_frames=max_frames, max_bytes=max_bytes)

    def test_append_snapshot_roundtrip(self):
        buf = self._make()
        self.assertTrue(buf.append({"pressure": 0.5, "status": 0}))
        self.assertTrue(buf.append({"pressure": 0.6, "status": 0}))
        self.assertEqual([f["pressure"] for f in buf.snapshot()], [0.5, 0.6])

    def test_clear(self):
        buf = self._make()
        buf.append({"pressure": 0.5})
        buf.clear()
        self.assertEqual(buf.snapshot(), [])

    def test_ignores_garbage_line(self):
        buf = self._make()
        buf.append({"pressure": 0.5})
        with open(self.path, "a") as handle:
            handle.write("this is not json\n")
            handle.write('{"pressure": 0.7}\n')
        self.assertEqual([f["pressure"] for f in buf.snapshot()], [0.5, 0.7])

    def test_partial_tail_line_from_power_cut(self):
        buf = self._make()
        buf.append({"pressure": 0.5})
        with open(self.path, "a") as handle:
            handle.write('{"pressure": 0.')  # no newline, truncated
        self.assertEqual([f["pressure"] for f in buf.snapshot()], [0.5])

    def test_trims_oldest_when_over_max_frames(self):
        buf = self._make(max_frames=3)
        for i in range(6):
            buf.append({"pressure": i})
        self.assertEqual([f["pressure"] for f in buf.snapshot()], [3, 4, 5])

    def test_trims_oldest_when_over_max_bytes(self):
        buf = self._make(max_frames=100, max_bytes=300)
        for i in range(10):
            buf.append({"pressure": i, "payload": "x" * 100})
        kept = buf.snapshot()
        self.assertLessEqual(len(kept), 4)
        self.assertEqual(kept, sorted(kept, key=lambda f: f["pressure"]))
        self.assertNotIn(0, [f["pressure"] for f in kept])


if __name__ == "__main__":
    unittest.main()