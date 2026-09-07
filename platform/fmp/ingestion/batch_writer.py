"""TimescaleDB batch writer: hypertable promotion + bulk time-series inserts.

``ensure_hypertables`` turns the plain ``measurements`` / ``station_totalizers``
tables into TimescaleDB hypertables (idempotent; safe to run on every app boot).
``insert_measurements`` performs a single multi-row INSERT per call so callers
can batch hundreds of readings per query.
"""
from __future__ import annotations

import logging

from sqlalchemy import text

logger = logging.getLogger(__name__)

HYPERTABLE_CONFIG = {
    "measurements": ("timestamp", "1 day"),
    "station_totalizers": ("created_at", "1 day"),
}


async def ensure_hypertables(session) -> list[str]:
    """Promote time-series tables to hypertables; returns names ensured/present."""
    await session.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))

    created: list[str] = []
    for table, (column, chunk_interval) in HYPERTABLE_CONFIG.items():
        await session.execute(text(
            f"SELECT create_hypertable(':table', ':column', "
            f"chunk_time_interval => INTERVAL ':interval', "
            f"if_not_exists => TRUE, migrate_data => TRUE)"
            .replace(":table", table)
            .replace(":column", column)
            .replace(":interval", chunk_interval)
        ))
        created.append(table)
        logger.info("hypertable ensured: %s (chunk %s)", table, chunk_interval)
    await session.commit()
    return created


async def insert_measurements(session, rows: list[dict]) -> int:
    """Bulk-insert measurement rows; returns the number of rows written."""
    from sqlalchemy.dialects.postgresql import insert

    from fmp.models import Measurement

    if not rows:
        return 0
    await session.execute(insert(Measurement), rows)
    return len(rows)