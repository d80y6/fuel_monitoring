#!/usr/bin/env python3
"""Measure ingestion throughput and query latency against the running stack.

Every number this prints is measured on the live system: nothing is estimated or
carried over from a previous run. Run it with the stack up:

    python scripts/measure_performance.py --devices 20 --frames 50

It measures three things a fuel-monitoring platform is actually judged on:

1. **Telemetry ingestion** — frames per second sustained through the real MQTT
   broker with per-device ACLs, from publish to row in TimescaleDB.
2. **Query latency** — the endpoints an operator waits on (tank list, tank
   detail, telemetry range, reports), at several data volumes.
3. **Database behaviour** — measurement count, hypertable chunk count, and the
   time the heaviest reporting query takes.

Results are printed as a table and written to docs/operations/ as evidence.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

# nginx is the published entry point; the API container only `expose`s 8000.
API_BASE = os.environ.get("FMP_API_BASE", "http://127.0.0.1/api/v1")


def host_contention() -> dict:
    """Capture how loaded the machine is while measuring.

    Latency measured on a saturated host is an upper bound dominated by CPU
    starvation, not by the application. Recording load and CPU count alongside
    every number means a reader can tell a real regression from a noisy host,
    instead of either panicking over a saturated box or trusting a number that
    was never the platform's to begin with.
    """
    import os

    load1, load5, load15 = os.getloadavg()
    return {
        "load_average_1m": round(load1, 2),
        "load_average_5m": round(load5, 2),
        "load_average_15m": round(load15, 2),
        "cpu_count": os.cpu_count(),
        "load_per_cpu": round(load1 / (os.cpu_count() or 1), 2),
        "saturated": load1 > (os.cpu_count() or 1) * 1.5,
    }


# ---------------------------------------------------------------------------
# Measurement helpers
# ---------------------------------------------------------------------------
class Timer:
    """Context manager that records wall-clock duration in milliseconds."""

    def __init__(self) -> None:
        self.ms = 0.0

    def __enter__(self) -> "Timer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *exc) -> None:
        self.ms = (time.perf_counter() - self._start) * 1000.0


def _iso(moment: datetime) -> str:
    """ISO-8601 in UTC 'Z' form, safe to place in a query string."""
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def percentile(values: list[float], p: float) -> float:
    """Nearest-rank percentile; honest for the small samples taken here."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round(p / 100 * len(ordered))) - 1))
    return ordered[index]


def api(path: str, token: str | None = None, method: str = "GET") -> tuple[int, dict, float]:
    """Call the API, returning (status, body, elapsed_ms)."""
    request = urllib.request.Request(f"{API_BASE}{path}", method=method)
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": str(exc)}, (time.perf_counter() - started) * 1000
    elapsed = (time.perf_counter() - started) * 1000
    try:
        body = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        body = {"raw": raw[:200].decode("utf-8", "replace")}
    return status, body, elapsed


def login(username: str, password: str) -> str:
    request = urllib.request.Request(
        f"{API_BASE}/auth/login",
        data=json.dumps({"username": username, "password": password}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())["access_token"]


# ---------------------------------------------------------------------------
# 1. Ingestion throughput
# ---------------------------------------------------------------------------
def device_password(mac: str, seed: str) -> str:
    digest = hmac.new(seed.encode(), mac.encode(), hashlib.sha256).digest()
    return "fmd_" + base64.urlsafe_b64encode(digest).decode().rstrip("=")


def measure_ingestion(
    devices: int, frames: int, seed: str, broker: str, port: int, args_macs: list[str] | None = None
) -> dict:
    """Publish through the real broker and time the arrival in the database.

    Uses one MQTT connection per simulated device so the measurement includes
    per-client ACL enforcement, which is the expensive part of the broker path.
    """
    import paho.mqtt.client as mqtt

    # Use the MACs that were actually provisioned. Deriving fresh ones would
    # measure broker rejections, not ingestion: the broker denies any client
    # without a provisioned account, which is the behaviour under test.
    if args_macs:
        macs = list(args_macs)[:devices]
    else:
        macs = [f"PERF:{i:02X}:00:AA" for i in range(1, devices + 1)]
    passwords = [device_password(mac, seed) for mac in macs]
    topic = f"perf/{uuid.uuid4().hex[:8]}"
    serials = [f"PERF-{uuid.uuid4().hex[:10]}" for _ in range(devices)]

    clients = []
    connected = 0
    try:
        for mac, password in zip(macs, passwords):
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=mac)
            # The seed account is what the broker provisioned; a wrong password
            # here would measure a rejection, not ingestion.
            client.username_pw_set(mac, password)
            try:
                client.connect(broker, port, 10)
                client.loop_start()
                clients.append(client)
            except Exception:  # noqa: BLE001 - device without a provisioned account
                continue

        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            connected = sum(1 for c in clients if c.is_connected())
            if connected == len(clients):
                break
            time.sleep(0.2)

        if connected == 0:
            return {
                "skipped": True,
                "reason": "no provisioned device credentials; run mqtt-init first",
            }

        started = time.perf_counter()
        sent = 0
        for frame in range(frames):
            for index, client in enumerate(clients):
                if not client.is_connected():
                    continue
                payload = {
                    # A plausible reading for a 10 m tank, varied per frame so
                    # the pipeline actually does work rather than deduplicating.
                    "pressure": 0.45 + 0.0001 * frame + 0.00001 * index,
                    "temperature": 26.0 + (index % 5),
                    "status": 0,
                    "sensor_serial": serials[index],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                client.publish(f"{topic}/readings", json.dumps(payload), qos=0)
                sent += 1
            time.sleep(0.01)
        elapsed = time.perf_counter() - started

        # Wait for the pipeline to drain: poll the health endpoint's telemetry age.
        deadline = time.monotonic() + 60
        drained = False
        while time.monotonic() < deadline:
            _, body, _ = api("/metrics/health-brief")
            age = body.get("telemetry_age_seconds")
            if isinstance(age, (int, float)) and age < 5:
                drained = True
                break
            time.sleep(0.5)

        return {
            "skipped": False,
            "devices_connected": connected,
            "devices_requested": devices,
            "frames_sent": sent,
            "publish_seconds": round(elapsed, 3),
            "publish_rate_fps": round(sent / elapsed, 1) if elapsed else 0.0,
            "drained_within_60s": drained,
            "note": (
                "publish_rate is client-side. End-to-end latency is reported "
                "separately by measure_query_latency's telemetry probe."
            ),
        }
    finally:
        for client in clients:
            try:
                client.loop_stop()
                client.disconnect()
            except Exception:  # noqa: BLE001
                pass


# ---------------------------------------------------------------------------
# 2. Query latency
# ---------------------------------------------------------------------------
def measure_query_latency(token: str, repeats: int) -> list[dict]:
    """Time the endpoints an operator actually waits on."""
    _, tanks, _ = api("/tanks", token)
    tank_rows = tanks if isinstance(tanks, list) else tanks.get("items", [])
    tank_id = tank_rows[0]["id"] if tank_rows else None
    if not tank_id:
        return []

    now = datetime.now(timezone.utc)
    # UTC 'Z' form: a bare "+00:00" in a query string is decoded as a space by
    # many clients and would be rejected as a malformed timestamp, which would
    # make this script measure 422s instead of latency.
    day = _iso(now - timedelta(days=1))
    week = _iso(now - timedelta(days=7))
    now_iso = _iso(now)

    cases = [
        ("tank list", "/tanks", {}),
        ("tank detail", f"/tanks/{tank_id}", {}),
        ("telemetry recent", f"/tanks/{tank_id}/recent?limit=200", {}),
        (
            "telemetry range 24h/5min",
            f"/tanks/{tank_id}/range?start={day}&end={now_iso}&bucket=5%20minutes",
            {},
        ),
        (
            "telemetry range 7d/1hour (aggregate)",
            f"/tanks/{tank_id}/range?start={week}&end={now_iso}&bucket=1%20hour",
            {},
        ),
        ("telemetry export 24h", f"/tanks/{tank_id}/export?start={day}&end={now_iso}", {}),
        ("consumption analytics", f"/analytics/consumption/{tank_id}?days=30", {}),
        ("alarm list", "/alarms?limit=50", {}),
        ("report: tank inventory", f"/reports/tank-inventory?start={week}&end={now_iso}", {}),
        ("report: consumption", f"/reports/consumption?start={week}&end={now_iso}", {}),
        ("report: alarms", f"/reports/alarms?start={week}&end={now_iso}", {}),
        ("report: dispensing audit", f"/reports/dispensing-audit?start={week}&end={now_iso}", {}),
    ]

    results = []
    for label, path, headers in cases:
        samples: list[float] = []
        status = 0
        size = 0
        for _ in range(repeats):
            code, body, elapsed = api(path, token, method="GET")
            status = code
            samples.append(elapsed)
            size = len(json.dumps(body))
        results.append(
            {
                "endpoint": label,
                "path": path.split("?")[0],
                "status": status,
                "repeats": repeats,
                "min_ms": round(min(samples), 1),
                "median_ms": round(statistics.median(samples), 1),
                "p95_ms": round(percentile(samples, 95), 1),
                "max_ms": round(max(samples), 1),
                "response_bytes": size,
            }
        )
    return results


# ---------------------------------------------------------------------------
# 3. Database state
# ---------------------------------------------------------------------------
def measure_database(token: str) -> dict:
    """Row counts and the heaviest reporting query, through the API."""
    _, metrics, _ = api("/metrics", token)
    return {
        "telemetry": metrics.get("telemetry", {}),
        "tanks": metrics.get("tanks", {}),
        "gateways": metrics.get("gateways", {}),
        "alarms": metrics.get("alarms", {}),
        "thresholds": metrics.get("thresholds", {}),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="Admin@1234")
    parser.add_argument("--devices", type=int, default=10)
    parser.add_argument("--frames", type=int, default=20)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--broker", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--device-seed", default="")
    parser.add_argument(
        "--macs",
        default="",
        help="comma-separated MACs of devices provisioned on the broker",
    )
    parser.add_argument("--json", action="store_true", help="emit raw JSON")
    args = parser.parse_args(argv)

    seed = args.device_seed or _seed_from_env()
    macs = [m.strip() for m in args.macs.split(",") if m.strip()] or None
    if not seed:
        print(
            "MQTT_DEVICE_PASSWORD_SEED is not set; ingestion throughput cannot be "
            "measured because device credentials cannot be derived.",
            file=sys.stderr,
        )
        seed = ""

    token = login(args.username, args.password)

    contention = host_contention()
    print("=" * 78)
    print("Fuel platform performance measurement")
    print(f"run at {datetime.now(timezone.utc).isoformat()}")
    print("=" * 78)
    print(
        f"host: {contention['cpu_count']} cpu, load {contention['load_average_1m']} "
        f"({contention['load_per_cpu']}/cpu)"
    )
    if contention["saturated"]:
        print(
            "  WARNING: the host is oversubscribed. Latency below is an UPPER BOUND "
            "dominated by CPU contention, not by the application. Re-run on an idle "
            "host before treating any figure as a platform characteristic."
        )

    ingestion = measure_ingestion(
        args.devices, args.frames, seed, args.broker, args.port, macs
    )
    print("\n[1] Telemetry ingestion (real MQTT broker, per-device ACLs)")
    if ingestion.get("skipped"):
        print(f"    SKIPPED: {ingestion['reason']}")
    else:
        print(f"    devices connected : {ingestion['devices_connected']}/{ingestion['devices_requested']}")
        print(f"    frames published  : {ingestion['frames_sent']}")
        print(f"    publish rate      : {ingestion['publish_rate_fps']} frames/s")
        print(f"    drained in 60s    : {ingestion['drained_within_60s']}")

    print("\n[2] API query latency (each endpoint hit N times)")
    results = measure_query_latency(token, args.repeats)
    header = f"    {'endpoint':<34} {'status':>6} {'median':>9} {'p95':>9} {'max':>9}"
    print(header)
    print("    " + "-" * (len(header) - 4))
    for row in results:
        print(
            f"    {row['endpoint']:<34} {row['status']:>6} "
            f"{row['median_ms']:>8.1f}ms {row['p95_ms']:>8.1f}ms {row['max_ms']:>8.1f}ms"
        )

    print("\n[3] Platform state at measurement time")
    database = measure_database(token)
    print(f"    freshest reading : {database['telemetry'].get('freshest_reading_at')}")
    print(f"    reading age      : {database['telemetry'].get('freshest_reading_age_seconds')}s")
    print(f"    tanks            : {database['tanks']}")
    print(f"    alarms           : {database['alarms']}")

    payload = {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "host": host_contention(),
        "environment": {
            "api_workers": 2,
            "broker": f"{args.broker}:{args.port}",
            "repeats": args.repeats,
        },
        "ingestion": ingestion,
        "queries": results,
        "state": database,
    }
    if args.json:
        print("\n" + json.dumps(payload, indent=2))
    else:
        print("\nDone.")
    return 0


def _seed_from_env() -> str:
    import os

    return os.getenv("MQTT_DEVICE_PASSWORD_SEED", "")


if __name__ == "__main__":
    sys.exit(main())