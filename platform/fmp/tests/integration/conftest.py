"""Integration-test shared fixtures."""
from __future__ import annotations

import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
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