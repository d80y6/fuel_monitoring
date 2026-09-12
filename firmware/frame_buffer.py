"""Bounded, crash-safe offline frame buffer for the edge gateway.

Stores JSON-lines in a single flash file (``path``). Oldest frames are trimmed
first to honour ``max_frames`` / ``max_bytes``. A line left half-written by a
power cut is discarded, not allowed to break the whole buffer.

Pure Python — host-testable; runs on MicroPython unchanged.
"""

import json
import os

_READ_CHUNK = 65536


def _iter_lines(path):
    try:
        handle = open(path, "r")
    except OSError:
        return
    with handle:
        while True:
            chunk = handle.read(_READ_CHUNK)
            if not chunk:
                break
            for line in chunk.splitlines():
                yield line


def _load_line(line: str):
    line = line.strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except ValueError:
        return None


class FrameBuffer:
    def __init__(self, path: str, max_frames: int = 2000,
                 max_bytes: int = 4 * 1024 * 1024):
        self.path = path
        self.max_frames = max_frames
        self.max_bytes = max_bytes

    def append(self, frame: dict) -> bool:
        try:
            with open(self.path, "a") as handle:
                handle.write(json.dumps(frame, separators=(",", ":")) + "\n")
        except OSError:
            return False
        self._trim()
        return True

    def snapshot(self) -> list[dict]:
        frames = []
        for frame in (x for x in (_load_line(line) for line in _iter_lines(self.path))
                      if x is not None):
            frames.append(frame)
        return frames

    def clear(self) -> None:
        try:
            os.remove(self.path)
        except OSError:
            pass

    def _trim(self) -> None:
        frames = self.snapshot()
        total = 0
        kept = []
        for frame in reversed(frames):
            size = len(json.dumps(frame, separators=(",", ":"))) + 1
            if total + size > self.max_bytes or len(kept) >= self.max_frames:
                continue
            kept.append(frame)
            total += size
        kept.reverse()
        if len(kept) == len(frames):
            return
        try:
            with open(self.path, "w") as handle:
                for frame in kept:
                    handle.write(json.dumps(frame, separators=(",", ":")) + "\n")
        except OSError:
            pass