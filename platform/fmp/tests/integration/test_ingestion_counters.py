"""Ingestion frame accounting.

Frame loss used to be visible only as a log line. These counters exist so a
burst that overwhelms the broker or the intake queue shows up on
``/api/v1/metrics`` as ``frames_unaccounted`` instead of silently shrinking the
fuel ledger.
"""

from __future__ import annotations

import pytest

from fmp.ingestion import metrics_counters as counters

KEYS = (
    counters.RECEIVED,
    counters.PERSISTED,
    counters.REJECTED,
    counters.DROPPED,
    counters.BATCHES,
    counters.BATCH_LATEST,
    counters.BATCH_MAX,
    counters.QUEUE_DEPTH,
)


@pytest.fixture(scope="module")
def requires_infra():
    return True


async def _redis():
    from fmp.core.redis import get_redis

    return await get_redis()


@pytest.fixture
async def clean_counters(requires_infra):
    redis = await _redis()
    await redis.delete(*KEYS)
    yield redis
    await redis.delete(*KEYS)
    await redis.aclose()


async def test_counters_accumulate(clean_counters):
    redis = clean_counters
    await counters.record_received(redis, 10)
    await counters.record_received(redis, 5)
    await counters.record_persisted(redis, 12)
    await counters.record_rejected(redis, 3)
    await counters.record_dropped(redis, 1)

    snap = await counters.snapshot(redis)
    assert snap["received"] == 15
    assert snap["persisted"] == 12
    assert snap["rejected_no_tank"] == 3
    assert snap["dropped_queue_full"] == 1


async def test_missing_counters_read_as_zero_not_error(clean_counters):
    """A fresh deployment must report zeros, not fail the metrics endpoint."""
    snap = await counters.snapshot(clean_counters)
    assert snap == {
        "received": 0,
        "persisted": 0,
        "rejected_no_tank": 0,
        "dropped_queue_full": 0,
        "queue_depth": 0,
        "batches": 0,
        "batch_latency_ms": 0,
        "batch_latency_ms_max": 0,
    }


async def test_record_batch_tracks_latest_depth_and_peak_latency(clean_counters):
    redis = clean_counters
    await counters.record_batch(redis, size=100, latency_ms=250.0, depth=5)
    await counters.record_batch(redis, size=400, latency_ms=90.0, depth=0)

    snap = await counters.snapshot(redis)
    assert snap["batches"] == 2
    assert snap["batch_latency_ms"] == 90, "latest batch latency should win"
    assert snap["batch_latency_ms_max"] == 250, "peak latency must survive a fast batch"
    assert snap["queue_depth"] == 0, "depth reflects the queue after the flush"


async def test_record_batch_never_raises():
    """Metrics must not be able to take ingestion down."""

    class Broken:
        def pipeline(self, **kwargs):
            raise RuntimeError("redis down")

        def __getattr__(self, name):
            def _raise(*args, **kwargs):
                raise RuntimeError("redis down")

            return _raise

    await counters.record_batch(Broken(), size=10, latency_ms=5.0, depth=1)


async def test_metrics_endpoint_exposes_ingestion_accounting(client):
    import json as _json

    resp = await client.get("/api/v1/metrics")
    assert resp.status_code == 200
    ingestion = _json.loads(resp.text)["ingestion"]
    assert ingestion["available"] is True
    for field in (
        "frames_received",
        "frames_persisted",
        "frames_unaccounted",
        "frames_dropped_queue_full",
        "queue_depth",
        "delivery_ratio",
    ):
        assert field in ingestion, f"metrics must report {field}"