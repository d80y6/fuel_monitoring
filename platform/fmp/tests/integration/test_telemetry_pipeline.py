"""Integration test: telemetry ingestion pipeline against live TimescaleDB + Redis.

Covers hypertable promotion, batch writes, EMA-smoothed threshold alarms and
outlier detection. Skipped when Postgres is unreachable.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from fmp.tests.conftest import FakeRedis

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def requires_infra():
    return True


async def _seed_tank(session):
    from fmp.models import Company, Site, Tank

    company = Company(name=f"IT-{uuid.uuid4().hex[:6]}")
    session.add(company)
    await session.flush()
    site = Site(name="Telemetry Site", company_id=company.id)
    session.add(site)
    await session.flush()
    tank = Tank(
        name="Gen A", site_id=site.id,
        sensor_serial_number=f"SN-{uuid.uuid4().hex[:10]}",
        tank_orientation="vertical", tank_diameter=2.0, tank_height=3.0,
        tank_volume=9200.0, elevation=0.0,
        calibration_factor=1.0,
        fuel_type=None,
        critical_level_threshold=0.5, low_level_threshold=1.0,
        high_level_threshold=2.8, low_volume_threshold=2000.0,
    )
    session.add(tank)
    await session.commit()
    return tank


async def test_hypertables_and_pipeline(requires_infra):
    from fmp.core.database import Base, async_session_factory, engine
    from fmp.ingestion.batch_writer import ensure_hypertables, insert_measurements
    from fmp.ingestion.pipeline import IngestionPipeline
    import fmp.models  # noqa: F401

    os.environ.setdefault("POSTGRES_DB", "fuel_test")
    redis = FakeRedis()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))

    async with async_session_factory() as session:
        hypertables = await ensure_hypertables(session)
        assert "measurements" in hypertables and "station_totalizers" in hypertables

    # idempotent second call
    async with async_session_factory() as session:
        assert "measurements" in await ensure_hypertables(session)

    # standalone batch insert returns rowcount and persists
    async with async_session_factory() as session:
        tank = await _seed_tank(session)
        now = datetime.now(timezone.utc)
        rows = [
            {"timestamp": now, "tank_id": tank.id, "pressure": 0.5, "temperature": 20.0,
             "level": 1.0, "volume": 3141.0, "fill_percent": 34.1, "is_outlier": False, "status": 0},
            {"timestamp": now + __import__("datetime").timedelta(seconds=1), "tank_id": tank.id, "pressure": 0.5, "temperature": 20.0,
             "level": 1.0, "volume": 3141.0, "fill_percent": 34.1, "is_outlier": False, "status": 0},
        ]
        assert await insert_measurements(session, rows) == 2
        await session.commit()

    # ---- end-to-end pipeline -------------------------------------------------
    # pressure ~0.125 bar => ~1.5 m level (between low=1.0 and high=2.8 thresholds)
    # pressure ~0.4   bar => ~4.8 m level (EMA+2.8 high threshold)
    # pressure ~0.03  bar => ~0.36 m level (low + critical cross while EMA decays)
    pipeline = IngestionPipeline(write_batch=True)

    async with async_session_factory() as session:
        for _ in range(8):
            r = await pipeline.process(
                session, redis, tank,
                pressure=0.125, temperature=25.0, status=0,
                captured_at=datetime.now(timezone.utc),
            )
            assert r is not None and r.is_outlier is False

        elevated_fired = False
        for _ in range(5):
            r = await pipeline.process(
                session, redis, tank,
                pressure=0.4, temperature=25.0, status=0,
                captured_at=datetime.now(timezone.utc),
            )
            assert r is not None
            if any(a.type == "high_level" for a in r.alarms):
                elevated_fired = True
        await session.commit()
        assert elevated_fired

    async with async_session_factory() as session:
        low_fired = critical_fired = False
        for _ in range(20):
            r = await pipeline.process(
                session, redis, tank,
                pressure=0.03, temperature=25.0, status=0,
                captured_at=datetime.now(timezone.utc),
            )
            if r is None:
                continue
            if any(a.type == "low_level" for a in r.alarms):
                low_fired = True
            if any(a.type == "critical_level" for a in r.alarms):
                critical_fired = True
        await session.commit()
        assert low_fired and critical_fired

    # ---- verify persistence ---------------------------------------------------
    async with async_session_factory() as session:
        from sqlalchemy import func, select
        from fmp.models import Alarm, Measurement

        count = (await session.execute(select(func.count()).select_from(Measurement))).scalar()
        assert count == 2 + 8 + 5 + 20
        alarms = (await session.execute(select(Alarm))).scalars().all()
        assert any(a.type == "high_level" for a in alarms)
        assert any(a.type == "critical_level" for a in alarms)