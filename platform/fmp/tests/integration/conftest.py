"""Integration-test shared fixtures."""
from __future__ import annotations

import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text


@pytest.fixture(autouse=True)
def _reset_login_rate_limit():
    """Clear login-throttle counters between tests.

    Integration tests log in repeatedly as the same username from one IP, which
    the production limiter (5 failures / 15 min per username+IP) correctly reads
    as brute force. Clearing the counters restores a clean slate *without*
    changing the configured threshold, so the tests that assert on the limiter's
    real behaviour still exercise it.
    """
    from fmp.api.v1.auth import _fallback_attempts

    _fallback_attempts.clear()
    try:
        from fmp.core.redis import get_redis_client

        async def _clear():
            client = await get_redis_client()
            keys = await client.client.keys("ratelimit:login:*")
            if keys:
                await client.client.delete(*keys)

        import asyncio

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(_clear())
    except Exception:  # Redis unreachable — the in-process fallback is cleared above
        pass
    yield
    _fallback_attempts.clear()


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
    import fmp.models  # noqa: F401
    from fmp.core.database import Base, async_session_factory, engine
    from fmp.ingestion.batch_writer import ensure_hypertables

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
    async with async_session_factory() as session:
        await ensure_hypertables(session)
    yield
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db):
    """AsyncClient with admin auth override for integration tests."""
    from fmp.api.deps import get_current_user
    from fmp.api.main import app
    from fmp.core.database import async_session_factory
    from fmp.core.security import hash_password
    from fmp.models import Company, Dispenser, Site, Station, User

    async with async_session_factory() as session:
        admin = User(
            username="test_admin",
            email="admin@test.io",
            password_hash=hash_password("TestPass123"),
            role="admin",
            is_active=True,
        )
        session.add(admin)

        company = Company(name="TestCo")
        session.add(company)
        await session.flush()

        site = Site(name="TestSite", company_id=company.id)
        session.add(site)
        await session.flush()

        station = Station(name="TestStation", site_id=site.id, serial_number="ST-TEST01")
        session.add(station)
        await session.flush()

        dispenser = Dispenser(name="TestPump", station_id=station.id, serial_number="DN-TEST01")
        session.add(dispenser)
        await session.commit()

    async def _override():
        return admin

    app.dependency_overrides[get_current_user] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()