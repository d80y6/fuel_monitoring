"""TimescaleDB lifecycle policies: continuous aggregates + refresh policies,
compression, and retention.

``ensure_timescale_policies`` is the idempotent, boot-safe counterpart to
``fmp.ingestion.batch_writer.ensure_hypertables``. It materializes hourly/daily
aggregates of ``measurements``, attaches refresh policies to them (a root-cause
fix for the legacy platform, whose continuous aggregates had *no* refresh policy),
enables compression, and installs the retention policy that caps raw-row growth.

TimescaleDB refuses to create continuous aggregates or scheduling policies inside
a transaction block, so this module drives that DDL through a dedicated
autocommit engine connection rather than the caller's session.
"""
from __future__ import annotations

import logging
import re

from sqlalchemy import text

from fmp.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

#: aggregate view name → (bucket interval, refresh start, refresh end, refresh
#: schedule). The refresh window (start minus end) must span at least two buckets
#: for that aggregate's bucket width.
_CONTINUOUS_AGGREGATES = {
    "measurements_hourly": ("1 hour", "3 hours", "1 hour", "1 hour"),
    "measurements_daily": ("1 day", "3 days", "1 day", "1 day"),
}

_AGG_SELECT = """
    SELECT
    time_bucket('{bucket_interval}', timestamp) AS bucket,
    tank_id,
    avg(pressure)                       AS pressure,
    avg(temperature)                    AS temperature,
    avg(level)                          AS level,
    avg(volume)                         AS volume,
    avg(gov_volume)                     AS gov_volume,
    avg(net_volume)                     AS net_volume,
    avg(density_at_temperature)         AS density_at_temperature,
    max(fill_percent)                   AS fill_percent,
    count(*)                            AS reading_count
"""


async def ensure_continuous_aggregates(conn) -> list[str]:
    """Create the hourly/daily materialized aggregates (idempotent).

    ``conn`` must be an autocommit connection — TimescaleDB disallows cagg
    creation inside a transaction block.
    """
    groups = []
    for view, (bucket_interval, _start, _end, _schedule) in _CONTINUOUS_AGGREGATES.items():
        await conn.execute(text(
            f"CREATE MATERIALIZED VIEW IF NOT EXISTS {view} "
            f"WITH (timescaledb.continuous) AS "
            f"{_AGG_SELECT.format(bucket_interval=bucket_interval)} "
            f"FROM measurements GROUP BY bucket, tank_id"
        ))
        groups.append(view)
        logger.info("continuous aggregate ensured: %s", view)
    return groups


async def ensure_cagg_refresh_policies(conn) -> None:
    """Attach refresh policies to the aggregates (idempotent)."""
    for view, (_bucket_interval, start, end, schedule) in _CONTINUOUS_AGGREGATES.items():
        await conn.execute(text(
            f"SELECT add_continuous_aggregate_policy('{view}', "
            f"INTERVAL '{start}', INTERVAL '{end}', INTERVAL '{schedule}', "
            f"if_not_exists => true)"
        ))
        logger.info("refresh policy attached to %s", view)


async def ensure_compression(conn) -> None:
    """Enable compression on the hypertable and its aggregates (idempotent)."""
    await conn.execute(text(
        "ALTER TABLE measurements SET (timescaledb.compress = true, "
        "timescaledb.compress_segmentby = 'tank_id')"
    ))
    for view in _CONTINUOUS_AGGREGATES:
        await conn.execute(text(
            f"ALTER MATERIALIZED VIEW {view} SET (timescaledb.compress = true)"
        ))
    await conn.execute(text(
        f"SELECT add_compression_policy('measurements', "
        f"INTERVAL '{settings.TSDB_COMPRESSION_AFTER_DAYS} days', if_not_exists => true)"
    ))
    logger.info("compression policy installed (%sd)", settings.TSDB_COMPRESSION_AFTER_DAYS)


async def ensure_retention(conn) -> None:
    """Install the raw-measurement retention policy (idempotent)."""
    await conn.execute(text(
        f"SELECT add_retention_policy('measurements', "
        f"INTERVAL '{settings.TSDB_MEASUREMENTS_RETENTION_DAYS} days', if_not_exists => true)"
    ))
    logger.info("retention policy installed (%sd)", settings.TSDB_MEASUREMENTS_RETENTION_DAYS)


async def _ddl_engine():
    """Short-lived autocommit engine (TimescaleDB DDL can't run in a txn)."""
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from fmp.core.database import engine as app_engine

    return create_async_engine(
        app_engine.url,
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )


async def ensure_timescale_policies(session) -> list[str]:
    """Apply every lifecycle policy; returns the ensured aggregate names.

    ``session`` is used only to promote hypertables (a plain transactional op).
    The aggregate/policy DDL itself runs on a dedicated autocommit engine
    because TimescaleDB refuses to create continuous aggregates or scheduling
    jobs inside a transaction block. Safe to call on every app boot — every
    step is guarded.

    .. note::
       ``conn`` parameters in the ``ensure_*`` helpers are that autocommit
       connection, not the caller's session.
    """
    from fmp.ingestion.batch_writer import ensure_hypertables

    await ensure_hypertables(session)

    ddl_engine = await _ddl_engine()
    try:
        async with ddl_engine.connect() as conn:
            views = await ensure_continuous_aggregates(conn)
            await ensure_cagg_refresh_policies(conn)
            await ensure_compression(conn)
            await ensure_retention(conn)
    finally:
        await ddl_engine.dispose()
    return views


async def refresh_continuous_aggregates(start, end) -> None:
    """Manually materialize every aggregate over ``[start, end]``.

    The refresh procedure refuses to run inside a transaction block, so it too
    goes through the autocommit engine, and it rejects windows narrower than a
    bucket, so aggregates whose bucket does not fit the window are skipped.
    ``start``/``end`` are trusted internal timestamps, formatted inline.
    """
    window = (end - start).total_seconds()
    ddl_engine = await _ddl_engine()
    try:
        async with ddl_engine.connect() as conn:
            for view, (bucket_interval, _start, _end, _schedule) in _CONTINUOUS_AGGREGATES.items():
                bucket_seconds = granularity_seconds(f"1 {bucket_interval}")
                if bucket_seconds is None or window < 2 * bucket_seconds:
                    continue
                await conn.execute(text(
                    f"CALL refresh_continuous_aggregate('{view}', "
                    f"'{start.isoformat()}', '{end.isoformat()}')"
                ))
    finally:
        await ddl_engine.dispose()


# --- /range aggregation routing ------------------------------------------------
_UNIT_SECONDS = {
    "second": 1, "seconds": 1,
    "minute": 60, "minutes": 60,
    "hour": 3600, "hours": 3600,
    "day": 86400, "days": 86400,
    "week": 604800, "weeks": 604800,
}

_BUCKET_RE = re.compile(r"^\s*(\d+)\s*([a-zA-Z]+)\s*$")

HOUR = 3600
DAY = 86400


def granularity_seconds(bucket: str) -> int | None:
    """``'5 minutes'`` → 300, ``'1 hour'`` → 3600; None when unparseable."""
    m = _BUCKET_RE.match(bucket)
    if not m:
        return None
    factor = _UNIT_SECONDS.get(m.group(2).lower())
    if factor is None:
        return None
    return int(m.group(1)) * factor


def choose_cagg(bucket: str, window_seconds: float) -> str | None:
    """Pick the materialized aggregate that should back a ``/range`` query.

    Only hourly-bucketed and coarser queries ride the aggregates (they carry
    one dot per bucket regardless of window); sub-hour colorizations stay on raw
    rows. A window narrower than two buckets is never worth the aggregate read.
    """
    if window_seconds < 0:
        return None
    granularity = granularity_seconds(bucket)
    if granularity == HOUR:
        return "measurements_hourly" if window_seconds >= 2 * HOUR else None
    if granularity is not None and granularity >= DAY:
        return "measurements_daily" if window_seconds >= 2 * DAY else None
    return None