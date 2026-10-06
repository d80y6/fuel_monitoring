"""One-shot DB bootstrap: create tables (baseline) + Alembic upgrades + seeds.

Run as a compose init service before API/ingest start:
    python -m fmp.scripts.init_db

Schema strategy (documented in docs/operations/database-migrations.md):
  1. ``Base.metadata.create_all`` brings a brand-new database straight to the
     current model shape (idempotent, ``checkfirst=True``).
  2. ``alembic upgrade head`` then applies guarded delta revisions (0001, 0002,
     ...) so databases created by *older* releases converge to the same shape.
     On a database that never ran Alembic, the version table is created
     automatically; steps are no-op where the model DDL already exists.
  3. TimescaleDB hypertables + continuous-aggregate/retention policies.
  4. Idempotent seeds: built-in fuel types, default admin.

This function is safe to re-run on every deploy.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy import text

_PLATFORM_ROOT = Path(__file__).resolve().parents[2]


def run_alembic_upgrade_head() -> None:
    """Apply the Alembic chain to ``head`` using the platform's alembic.ini."""
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(_PLATFORM_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_PLATFORM_ROOT / "alembic"))
    command.upgrade(cfg, "head")


async def init_db() -> None:
    import fmp.models  # noqa: F401  (register all model tables)
    from fmp.core.config import settings
    from fmp.core.database import Base, async_session_factory, engine
    from fmp.ingestion.batch_writer import ensure_hypertables
    from fmp.scripts.seed_admin import seed_admin
    from fmp.scripts.seed_fuel_types import seed_fuel_types
    from fmp.ingestion.tsdb_policies import ensure_timescale_policies

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
        await conn.run_sync(Base.metadata.create_all)

    # Apply guarded delta revisions (safe on fresh DBs: all steps no-op).
    await asyncio.to_thread(run_alembic_upgrade_head)

    await seed_fuel_types(engine)

    if settings.ADMIN_PASSWORD:
        await seed_admin(engine)

    async with async_session_factory() as session:
        await ensure_hypertables(session)
        await ensure_timescale_policies(session)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_db())
