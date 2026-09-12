"""ESP32 board helpers: identity, uptime, reset cause, watchdog.

Device-only module; not imported by host tests.
"""

import machine
import time

_WDT_MAX_MS = 8000


def mac_address() -> str:
    """STA MAC as ``AA:BB:CC:DD:EE:01``."""
    import network

    wlan = network.WLAN(network.STA_IF)
    if not wlan.active():
        wlan.active(True)
    mac = wlan.config("mac")
    return ":".join("%02X" % byte for byte in mac)


def uptime_s() -> int:
    return int(time.ticks_ms() / 1000)


def reset_cause_name() -> str:
    RESET_CAUSES = {
        machine.PWRON_RESET: "power_on",
        machine.HARD_RESET: "hard_reset",
        machine.WDT_RESET: "watchdog",
        machine.DEEPSLEEP_RESET: "deep_sleep",
        machine.SOFT_RESET: "soft_reset",
    }
    return RESET_CAUSES.get(machine.reset_cause(), "unknown")


def rssi_dbm() -> int:
    import network

    wlan = network.WLAN(network.STA_IF)
    try:
        rssi = wlan.status("rssi")
        if isinstance(rssi, tuple):
            return int(rssi[-1])
        return int(rssi)
    except (ValueError, OSError):
        return -127


def free_ram_bytes() -> int:
    import gc

    gc.collect()
    return gc.mem_free()


class Watchdog:
    def __init__(self, timeout_s: int):
        self._wdt = machine.WDT(timeout=min(int(timeout_s * 1000), _WDT_MAX_MS))

    def feed(self) -> None:
        self._wdt.feed()


def reboot() -> None:
    machine.reset()