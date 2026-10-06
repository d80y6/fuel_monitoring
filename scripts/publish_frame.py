#!/usr/bin/env python3
"""Publish a tank telemetry frame as a real MQTT device (workflow 3/4/5/6).

Credentials are derived the same way `fmp.scripts.provision_mqtt_accounts`
derives them, so this exercises the real per-device ACL path: a device can only
publish on `fuel/<its-own-mac>/#`.

Usage:
    publish_frame.py <MAC> <pressure_bar> [temperature_c]
    publish_frame.py <MAC> --raw '<json payload>'
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import sys
import time

import paho.mqtt.client as mqtt

SEED = "local-dev-fleet-seed-change-me"
BROKER = "emqx"
PORT = 1883


def device_password(mac: str) -> str:
    digest = hmac.new(SEED.encode(), mac.encode(), hashlib.sha256).digest()
    return "fmd_" + base64.urlsafe_b64encode(digest).decode().rstrip("=")


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    mac = sys.argv[1]
    if sys.argv[2] == "--raw":
        payload = json.loads(sys.argv[3])
    else:
        pressure = float(sys.argv[2])
        temperature = float(sys.argv[3]) if len(sys.argv) > 3 else 28.0
        payload = {
            "pressure": pressure,
            "temperature": temperature,
            "status": 0,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
        }

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=mac)
    client.username_pw_set(mac, device_password(mac))
    try:
        client.connect(BROKER, PORT, 15)
    except Exception as exc:
        print(f"CONNECT REJECTED: {exc}")
        return 1
    client.loop_start()
    time.sleep(1.0)
    if not client.is_connected():
        print("CONNECT REJECTED: broker refused the device credentials")
        client.disconnect()
        return 1
    client.publish(f"fuel/{mac}/readings", json.dumps(payload), qos=1)
    client.loop_stop()
    time.sleep(1.0)
    client.disconnect()
    print(f"published pressure={payload.get('pressure')} on fuel/{mac}/readings")
    return 0


if __name__ == "__main__":
    sys.exit(main())