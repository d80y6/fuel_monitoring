"""One-shot DB bootstrap: create tables + promote hypertables.

Run as a compose init service before API/ingest start:
    python -m fmp.scripts.init_db
Re-runnable: model create_all is idempotent via checkfirst, and
ensure_hypertables uses IF NOT EXISTS semantics.
"""
from __future__ import annotations

import asyncio

from sqlalchemy import text


async def init_db() -> None:
    from fmp.core.database import Base, async_session_factory, engine
    from fmp.ingestion.batch_writer import ensure_hypertables

    import fmp.models  # noqa: F401  (register all model tables)

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as session:
        await ensure_hypertables(session)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_db())