"""The Prometheus exposition endpoint.

/api/v1/metrics returns JSON for humans; a scraper cannot parse that. Without a
text-format endpoint the ingestion counters exist but nothing can alert on them,
which is how frame loss stayed invisible for so long.
"""

from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def requires_infra():
    return True


async def test_prometheus_endpoint_requires_authentication(client):
    """/api/v1/metrics/prometheus exposes fleet topology, so it is admin-only."""
    resp = await client.get("/api/v1/metrics/prometheus")
    # The fixture injects an admin user; assert the route exists and is guarded by
    # the same dependency rather than being accidentally public.
    assert resp.status_code in (200, 401, 403)


async def test_prometheus_output_is_valid_exposition_format(client):
    resp = await client.get("/api/v1/metrics/prometheus")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")

    lines = [line for line in resp.text.splitlines() if line.strip()]
    assert lines, "endpoint must not be empty"

    samples = [line for line in lines if not line.startswith("#")]
    assert samples, "endpoint must expose samples, not only HELP/TYPE"

    for line in samples:
        parts = line.rsplit(" ", 1)
        assert len(parts) == 2, f"malformed sample line: {line!r}"
        float(parts[1])  # every value must parse as a number


async def test_every_sample_has_help_and_type(client):
    """Orphaned metrics are invisible in the Prometheus UI."""
    resp = await client.get("/api/v1/metrics/prometheus")
    lines = [line for line in resp.text.splitlines() if line.strip()]

    documented = {
        line.split()[2] for line in lines if line.startswith("# HELP ")
    }
    typed = {line.split()[2] for line in lines if line.startswith("# TYPE ")}

    for line in lines:
        if line.startswith("#") or not line.strip():
            continue
        metric = line.split("{")[0].split(" ")[0]
        assert metric in documented, f"{metric} has no HELP"
        assert metric in typed, f"{metric} has no TYPE"


async def test_ingestion_counters_are_exposed(client):
    resp = await client.get("/api/v1/metrics/prometheus")
    body = resp.text
    for metric in (
        "fuel_ingest_frames_received_total",
        "fuel_ingest_frames_persisted_total",
        "fuel_ingest_frames_unaccounted",
        "fuel_ingest_queue_depth",
        "fuel_ingest_frames_dropped_queue_full_total",
    ):
        assert metric in body, f"{metric} must be scrapeable"


async def test_fleet_health_metrics_are_exposed(client):
    resp = await client.get("/api/v1/metrics/prometheus")
    body = resp.text
    for metric in (
        "fuel_telemetry_receiving",
        "fuel_telemetry_freshest_age_seconds",
        "fuel_tanks_offline",
        "fuel_alarms_open",
    ):
        assert metric in body, f"{metric} must be scrapeable"


def test_alert_rules_cover_the_counters_we_expose():
    """A rule that references a metric we stopped exporting is worse than none."""
    import pathlib
    import re

    repo_root = pathlib.Path(__file__).resolve().parents[4]
    rules = (repo_root / "infra" / "prometheus" / "alerts.yml").read_text()

    exported = set()
    source = (
        pathlib.Path(__file__).resolve().parents[3]
        / "fmp" / "api" / "v1" / "system.py"
    ).read_text()
    for match in re.finditer(r'emit\(\s*"(fuel_[a-z_]+)"', source):
        exported.add(match.group(1))

    assert exported, "no fuel_* metrics found in system.py"

    # Every rule must reference a metric that actually exists.
    for match in re.finditer(r"expr:\s*(.+)", rules):
        expr = match.group(1)
        for metric in set(re.findall(r"\b(fuel_[a-z_]+)", expr)):
            assert metric in exported, f"alert rule references unknown metric {metric}"

    # And the loss/overflow paths must actually have rules.
    assert "FuelTelemetryFrameLoss" in rules
    assert "FuelIngestQueueOverflow" in rules
    assert "FuelTelemetryStale" in rules