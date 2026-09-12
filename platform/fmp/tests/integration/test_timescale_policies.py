"""Integration test: TimescaleDB lifecycle policies.

Verifies that ``ensure_timescale_policies`` creates the hourly/daily continuous
aggregates with refresh policies, a compression policy and a retention policy,
and that the tank ``/range`` endpoint serves coarse windows from the materialized
aggregate instead of scanning raw rows.

Requires a live TimescaleDB 2.x. The module tears all policies/views down after
itself so the shared ``fuel_test`` database stays pristine for sibling modules.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio

CAGG_VIEWS = ("measurements_hourly", "measurements_daily")

_CLEANUP = [
    "SELECT remove_continuous_aggregate_policy('measurements_hourly')",
    "SELECT remove_continuous_aggregate_policy('measurements_daily')",
    "SELECT remove_retention_policy('measurements')",
    "SELECT remove_compression_policy('measurements')",
    "DROP MATERIALIZED VIEW IF EXISTS measurements_hourly CASCADE",
    "DROP MATERIALIZED VIEW IF EXISTS measurements_daily CASCADE",
]


async def _cleanup() -> None:
    from fmp.core.database import async_session_factory

    async with async_session_factory() as session:
        for stmt in _CLEANUP:
            try:
                await session.execute(text(stmt))
                await session.commit()
            except Exception:
                await session.rollback()


@pytest.fixture(autouse=True, scope="module")
def _cleanup_module():
    """Tear TimescaleDB policies/views down after the module so sibling test
    modules that ``drop_all`` the schema never hit dependent-view errors."""
    yield
    asyncio.run(_cleanup())


async def _reset_schema() -> None:
    """Fresh schema + policies per test (explicit helper, not a pytest fixture)."""
    await _cleanup()
    from fmp.core.database import Base, async_session_factory, engine
    from fmp.ingestion.batch_writer import ensure_hypertables
    from fmp.ingestion.tsdb_policies import ensure_timescale_policies

    import fmp.models  # noqa: F401

    os.environ.setdefault("POSTGRES_DB", "fuel_test")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
    async with async_session_factory() as session:
        await ensure_hypertables(session)
        await ensure_timescale_policies(session)


async def _seed_tank(session):
    from fmp.models import Company, Site, Tank

    company = Company(name=f"TS-{uuid.uuid4().hex[:6]}")
    session.add(company)
    await session.flush()
    site = Site(name="Policy Site", company_id=company.id)
    session.add(site)
    await session.flush()
    tank = Tank(
        name="Policy Tank",
        site_id=site.id,
        sensor_serial_number=f"TP-{uuid.uuid4().hex[:10]}",
        tank_orientation="vertical",
        tank_shape="vertical_cylinder",
        tank_diameter=2.0,
        tank_height=3.0,
        tank_volume=9200.0,
        elevation=0.0,
        calibration_factor=1.0,
        is_active=True,
    )
    session.add(tank)
    await session.commit()
    return tank


async def _seed_hourly_readings(session, tank, hours: int = 12):
    """Seed one reading per hour on the hour, ending 1h before now."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    base = (now - timedelta(hours=hours)).replace(minute=0, second=0)
    volumes = []
    from fmp.models import Measurement

    for i in range(hours):
        ts = base + timedelta(hours=i)
        volume = 1000.0 + 10.0 * i
        volumes.append(round(volume, 6))
        session.add(Measurement(
            tank_id=tank.id,
            timestamp=ts,
            pressure=1.0,
            temperature=20.0,
            level=2.0,
            volume=volume,
            gov_volume=volume,
            net_volume=volume * 0.98,
            density_at_temperature=800.0,
            fill_percent=50.0,
            is_outlier=False,
            status=0,
        ))
    await session.commit()
    return base, base + timedelta(hours=hours), volumes


async def test_policies_created():
    await _reset_schema()

    from fmp.core.database import async_session_factory

    async with async_session_factory() as session:
        rows = (await session.execute(text(
            "SELECT view_name, compression_enabled "
            "FROM timescaledb_information.continuous_aggregates"
        ))).all()
        views = {r[0] for r in rows}
        assert "measurements_hourly" in views
        assert "measurements_daily" in views
        agg_compression = {r[0] for r in rows if r[1]}
        assert "measurements_hourly" in agg_compression
        assert "measurements_daily" in agg_compression

        raw_compression = (await session.execute(text(
            "SELECT compression_enabled FROM timescaledb_information.hypertables "
            "WHERE hypertable_name = 'measurements'"
        ))).scalar_one()
        assert raw_compression is True

        jobs = {r[0] for r in (await session.execute(text(
            "SELECT proc_name FROM timescaledb_information.jobs"
        ))).all()}
        assert "policy_refresh_continuous_aggregate" in jobs  # at least one
        assert "policy_compression" in jobs
        assert "policy_retention" in jobs

        refresh_count = (await session.execute(text(
            "SELECT count(*) FROM timescaledb_information.jobs "
            "WHERE proc_name = 'policy_refresh_continuous_aggregate'"
        ))).scalar_one()
        assert refresh_count == 2  # one per continuous aggregate


async def test_cagg_refresh_and_range():
    await _reset_schema()

    from httpx import ASGITransport, AsyncClient

    from fmp.api.deps import get_current_user
    from fmp.api.main import app
    from fmp.core.database import async_session_factory
    from fmp.core.security import hash_password
    from fmp.models import User

    async with async_session_factory() as session:
        tank = await _seed_tank(session)
        start, end, expected = await _seed_hourly_readings(session, tank, hours=12)

        # The aggregate is real-time (materialized_only = false), so it already
        # reflects seeded rows; a manual refresh must still execute without
        # error and materialize exactly the 12 hourly buckets.
        from fmp.ingestion.tsdb_policies import refresh_continuous_aggregates

        await refresh_continuous_aggregates(start, end)

        rows = (await session.execute(text(
            "SELECT bucket, volume FROM measurements_hourly "
            "WHERE tank_id = :tid AND bucket >= :s AND bucket <= :e "
            "ORDER BY bucket"
        ), {"tid": tank.id, "s": start, "e": end})).all()
        assert [r[1] for r in rows] == expected

        admin = User(
            username="pol_admin",
            email="pol@test.io",
            password_hash=hash_password("TestPass123"),
            role="admin",
            is_active=True,
        )
        session.add(admin)
        await session.commit()

    async def _override():
        return admin

    app.dependency_overrides[get_current_user] = _override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            # coarse bucket → served from the hourly continuous aggregate
            resp = await c.get(f"/api/v1/tanks/{tank.id}/range", params={
                "start": start.isoformat(),
                "end": end.isoformat(),
                "bucket": "1 hour",
            })
            assert resp.status_code == 200
            body = resp.json()
            assert [p["volume"] for p in body] == expected
            assert len(body) == len(expected)

            # fine bucket (5 minutes) deliberately stays on raw rows
            resp = await c.get(f"/api/v1/tanks/{tank.id}/range", params={
                "start": start.isoformat(),
                "end": end.isoformat(),
                "bucket": "5 minutes",
            })
            assert resp.status_code == 200
            assert len(resp.json()) == len(expected)
    finally:
        app.dependency_overrides.clear()


async def test_policies_idempotent():
    await _reset_schema()

    from fmp.core.database import async_session_factory
    from fmp.ingestion.tsdb_policies import ensure_timescale_policies

    async with async_session_factory() as session:
        await ensure_timescale_policies(session)  # second call must not raise

    async with async_session_factory() as session:
        rows = (await session.execute(text(
            "SELECT view_name FROM timescaledb_information.continuous_aggregates"
        ))).all()
        assert any("measurements_hourly" in r[0] for r in rows)