"""WiFi station connectivity helper."""

import time


def ensure_wifi(ssid: str, password: str, *, timeout_s: float = 15.0) -> bool:
    import network

    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        return True
    wlan.connect(ssid, password)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if wlan.isconnected():
            return True
        time.sleep(0.2)
    return False


def is_connected() -> bool:
    import network

    return network.WLAN(network.STA_IF).isconnected()