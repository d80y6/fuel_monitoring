"""Offline buffer for ESP32-S3 MicroPython."""
import ujson


class OfflineBuffer:
    """Circular buffer with flash storage for offline operation.

    Stores up to max_size readings during network outages.
    Uses SPIFFS/LittleFS for persistent storage.
    Batch flushes to reduce flash wear.
    """

    def __init__(self, max_size=10000, filepath="/buffer/readings.json", flush_interval=10):
        self.max_size = max_size
        self.filepath = filepath
        self.flush_interval = flush_interval
        self._memory_buffer = []
        self._dirty_count = 0
        self._load_from_flash()

    def _load_from_flash(self):
        try:
            with open(self.filepath, 'r') as f:
                self._memory_buffer = ujson.load(f)
        except (OSError, ValueError):
            self._memory_buffer = []
        if not isinstance(self._memory_buffer, list):
            self._memory_buffer = []

    def _flush_to_flash(self):
        while len(self._memory_buffer) > self.max_size:
            self._memory_buffer = self._memory_buffer[len(self._memory_buffer) - self.max_size:]

        trimmed = self._memory_buffer[-self.max_size:]

        empty_written = False
        if not trimmed:
            try:
                with open(self.filepath, 'w') as f:
                    f.write('[]')
                empty_written = True
            except OSError:
                pass

        if not empty_written:
            try:
                with open(self.filepath, 'w') as f:
                    ujson.dump(trimmed, f)
            except OSError:
                return

        self._memory_buffer = trimmed
        self._dirty_count = 0

    def add(self, readings):
        if isinstance(readings, dict):
            readings = [readings]
        elif not isinstance(readings, list):
            raise TypeError("add() expects a list or dict, got %s" % type(readings).__name__)

        self._memory_buffer.extend(readings)
        self._dirty_count += len(readings)

        if len(self._memory_buffer) > self.max_size:
            excess = len(self._memory_buffer) - self.max_size
            self._memory_buffer = self._memory_buffer[excess:]

        if self._dirty_count >= self.flush_interval:
            self._flush_to_flash()

    def flush(self):
        if self._dirty_count > 0:
            self._flush_to_flash()

    def drain(self):
        readings = self._memory_buffer[:]
        try:
            with open(self.filepath, 'w') as f:
                f.write('[]')
        except OSError:
            pass
        self._memory_buffer = []
        self._dirty_count = 0
        return readings

    def __len__(self):
        return len(self._memory_buffer)

    @property
    def is_full(self):
        return len(self._memory_buffer) >= self.max_size

    def stats(self):
        return {
            "size": len(self._memory_buffer),
            "max_size": self.max_size,
            "filepath": self.filepath,
            "dirty": self._dirty_count
        }
