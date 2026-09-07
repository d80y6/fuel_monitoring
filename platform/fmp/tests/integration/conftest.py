"""Integration-test shared fixtures."""
from __future__ import annotations

import os

import pytest
import pytest_asyncio
from sqlalchemy import text


@pytest.fixture(autouse=True)
def _reset_dependency_overrides():
    """Clear any FastAPI dependency overrides left by a previous test."""
    from fmp.api.main import app

    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def db():
    """Fresh schema per test against the live TimescaleDB (fuel_test)."""
    os.environ.setdefault("POSTGRES_DB", "fuel_test")
    from fmp.core.database import Base, async_session_factory, engine
    from fmp.ingestion.batch_writer import ensure_hypertables

    import fmp.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
    async with async_session_factory() as session:
        await ensure_hypertables(session)
    yield
    await engine.dispose()