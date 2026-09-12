"""Integration test: daily consumption analytics + SMA forecast.

Seeds a tank with hourly readings spanning three full UTC days whose tank
volume decays by 10 L/hour. Each hourly drop is attributed to the day the fuel
was drawn (the day of the earlier sample), so every full day sums to 240 liters
and the simple-moving-average forecast is 240 L/day.

Covers the pure service, the Celery task (callable directly, stores persisted
summaries) and the public API endpoint.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

pytestmark = pytest.mark.asyncio


async def _seed_declining_volumes(session, days: int = 3, per_day: int = 24):
    """Hourly readings from UTC midnight through the closing reading.

    ``days*per_day + 1`` samples cover three full calendar days plus the reading
    that closes the final day (at the next midnight), so every seeded night
    yields a complete 24-hour row of deltas.
    """
    from fmp.models import Company, Site, Tank, Measurement

    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=days)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    company = Company(name=f"AN-{uuid.uuid4().hex[:6]}")
    session.add(company)
    await session.flush()
    site = Site(name="Consumption Site", company_id=company.id)
    session.add(site)
    await session.flush()
    tank = Tank(
        name="Consumption Tank",
        site_id=site.id,
        sensor_serial_number=f"ANSN-{uuid.uuid4().hex[:10]}",
        tank_orientation="vertical",
        tank_shape="vertical_cylinder",
        tank_diameter=2.0,
        tank_height=3.0,
        tank_volume=10000.0,
        elevation=0.0,
        calibration_factor=1.0,
        is_active=True,
    )
    session.add(tank)
    await session.flush()

    volume = 5000.0
    for i in range(days * per_day + 1):
        ts = start + timedelta(hours=i)
        session.add(Measurement(
            tank_id=tank.id,
            timestamp=ts,
            pressure=1.0,
            temperature=20.0,
            level=1.0,
            volume=volume,
            fill_percent=50.0,
            is_outlier=False,
            status=0,
        ))
        volume -= 10.0
    await session.commit()
    return tank, start


async def test_daily_consumption_and_sma_forecast_api(client):
    from fmp.core.database import async_session_factory

    async with async_session_factory() as session:
        tank, start = await _seed_declining_volumes(session, days=3)

    expected_days = [
        (start.date().isoformat(), 240.0),
        ((start + timedelta(days=1)).date().isoformat(), 240.0),
        ((start + timedelta(days=2)).date().isoformat(), 240.0),
    ]

    resp = await client.get(
        f"/api/v1/analytics/consumption/{tank.id}",
        params={"days": 3, "window_days": 7},
    )
    assert resp.status_code == 200
    payload = resp.json()

    assert payload["method"] == "sma"
    assert payload["forecast"]["liters_per_day"] == pytest.approx(240.0, abs=1e-3)
    series = [(p["date"], p["liters"]) for p in payload["series"]]
    assert series == expected_days


async def test_celery_task_computes_and_upserts_summaries(client):
    from fmp.core.database import async_session_factory

    async with async_session_factory() as session:
        tank, start = await _seed_declining_volumes(session, days=3)

    # The Celery task body is a thin async→sync wrapper; exercising its async
    # core keeps the loop-safe render (asyncio.run) out of the test event loop.
    from fmp.workers.tasks.analytics import _compute_and_store

    payload = await _compute_and_store(tank.id, days=3, window_days=7)
    assert payload["method"] == "sma"
    assert payload["forecast"]["liters_per_day"] == pytest.approx(240.0, abs=1e-3)
    assert len(payload["series"]) == 3

    async with async_session_factory() as session:
        from fmp.models import ConsumptionSummary

        rows = (
            await session.execute(
                select(ConsumptionSummary)
                .where(ConsumptionSummary.tank_id == tank.id)
                .order_by(ConsumptionSummary.day)
            )
        ).scalars().all()
        assert len(rows) == 3
        assert [r.liters for r in rows] == pytest.approx([240.0, 240.0, 240.0])
        assert all(r.forecast_liters_per_day == pytest.approx(240.0, abs=1e-3) for r in rows)


async def test_analytic_returns_404_for_unknown_tank(client):
    resp = await client.get(
        f"/api/v1/analytics/consumption/{uuid.uuid4()}", params={"days": 3}
    )
    assert resp.status_code == 404