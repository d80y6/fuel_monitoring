"""Network time sync + ISO-8601 timestamp helper.

Broken or unsynced device clocks only degrade ``timestamp`` fidelity — the
ingestion consumer falls back to its own ``utcnow()`` when the field is absent —
so sync failures are non-fatal.
"""

import time


def sync(host: str = "pool.ntp.org", timeout_s: float = 3.0) -> bool:
    try:
        import ntptime

        ntptime.host = host
        ntptime.settime()
        return True
    except (ImportError, OSError, ArithmeticError):
        return False


def iso_utc() -> str | None:
    """ISO-8601 UTC timestamp if the RTC holds a plausible date, else None."""

    tm = time.localtime()
    if tm[0] < 2021:
        return None
    return "%04d-%02d-%02dT%02d:%02d:%02dZ" % (
        tm[0], tm[1], tm[2], tm[3], tm[4], tm[5]
    )