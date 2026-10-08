"""Ingestion counters, published so frame loss is observable rather than silent.

Before this existed, a burst that overwhelmed the broker or the intake queue was
only visible as a log line. ``/api/v1/metrics`` reads these counters so an
operator can alert on ``received - persisted`` growing over time.

Redis is used rather than process memory because the counters must outlive the
ingestion container: ``ingest`` is the process that owns the numbers, and
``api`` is the process that serves them.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("ingestion")

PREFIX = "fmp:metric:ingest"

RECEIVED = f"{PREFIX}:received"
PERSISTED = f"{PREFIX}:persisted"
REJECTED = f"{PREFIX}:rejected_no_tank"
QUEUE_DEPTH = f"{PREFIX}:queue_depth"
DROPPED = f"{PREFIX}:dropped_queue_full"
BATCHES = f"{PREFIX}:batches"
BATCH_LATEST = f"{PREFIX}:batch_latency_ms"
BATCH_MAX = f"{PREFIX}:batch_latency_ms_max"

ALL_KEYS = (RECEIVED, PERSISTED, REJECTED, QUEUE_DEPTH, DROPPED, BATCHES, BATCH_LATEST, BATCH_MAX)


async def record_received(redis, count: int = 1) -> None:
    await redis.incrby(RECEIVED, count)


async def record_persisted(redis, count: int = 1) -> None:
    await redis.incrby(PERSISTED, count)


async def record_rejected(redis, count: int = 1) -> None:
    await redis.incrby(REJECTED, count)


async def record_dropped(redis, count: int = 1) -> None:
    await redis.incrby(DROPPED, count)


async def record_batch(redis, *, size: int, latency_ms: float, depth: int) -> None:
    """Record one completed flush. Counters must never break ingestion."""
    try:
        pipe = redis.pipeline(transaction=False)
        pipe.incrby(BATCHES, 1)
        pipe.set(BATCH_LATEST, latency_ms)
        pipe.set(QUEUE_DEPTH, depth)
        # Rolling worst case so a single stall stays visible after it passes.
        current_max = float(await redis.get(BATCH_MAX) or 0.0)
        if latency_ms > current_max:
            pipe.set(BATCH_MAX, latency_ms)
        await pipe.execute()
    except Exception:  # noqa: BLE001 — metrics must never drop telemetry
        logger.debug("failed to record ingestion batch metrics", exc_info=True)


FLOAT_KEYS = (BATCH_LATEST, BATCH_MAX)


async def snapshot(redis) -> dict[str, float]:
    """Read every counter, missing keys reported as 0."""
    values = await redis.mget(ALL_KEYS)
    out: dict[str, float] = {}
    for key, value in zip(ALL_KEYS, values, strict=True):
        if key in FLOAT_KEYS:
            out[key.rsplit(":", 1)[-1]] = float(value or 0.0)
        else:
            out[key.rsplit(":", 1)[-1]] = int(value or 0)
    return out