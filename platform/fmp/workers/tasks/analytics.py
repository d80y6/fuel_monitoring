"""Analytics tasks: daily consumption + SMA forecast persistence.

``compute_daily_consumption`` computes the consumption series for one tank and
upserts it into ``consumption_summaries`` so history accumulates at a fixed
cadence; ``compute_all_consumption`` fans out over every active, non-deleted
tank and is the daily beat entry.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, select

from fmp.models import ConsumptionSummary, Tank
from fmp.services.analytics.consumption import compute_consumption
from fmp.workers.celery_app import celery_app


async def _compute_and_store(tank_id, days: int, window_days: int) -> dict:
    from fmp.core.database import celery_session_factory

    payload = None
    async with celery_session_factory() as session:
        payload = await compute_consumption(
            session, tank_id, days=days, window_days=window_days
        )
    if payload["series"]:
        now = datetime.now(timezone.utc)
        lookback = date.today() - timedelta(days=days)
        forecast_value = payload["forecast"]["liters_per_day"]
        async with celery_session_factory() as session:
            await session.execute(
                delete(ConsumptionSummary).where(
                    ConsumptionSummary.tank_id == tank_id,
                    ConsumptionSummary.day >= lookback,
                )
            )
            for point in payload["series"]:
                session.add(ConsumptionSummary(
                    tank_id=tank_id,
                    day=date.fromisoformat(point["date"]),
                    liters=point["liters"],
                    forecast_liters_per_day=forecast_value,
                    forecast_window_days=window_days,
                ))
            await session.commit()
    return payload


def _tank_ids():
    from fmp.core.database import celery_session_factory

    async def _collect():
        async with celery_session_factory() as session:
            rows = await session.execute(
                select(Tank.id).where(
                    Tank.is_active.is_(True), Tank.deleted_at.is_(None)
                )
            )
            return [r for (r,) in rows]

    return asyncio.run(_collect())


@celery_app.task(name="analytics.compute_daily_consumption")
def compute_daily_consumption(tank_id: str, days: int = 30, window_days: int = 7) -> dict:
    """Compute + persist one tank's daily consumption summary."""
    return asyncio.run(_compute_and_store(uuid.UUID(tank_id), days, window_days))


@celery_app.task(name="analytics.compute_all_consumption")
def compute_all_consumption(days: int = 30, window_days: int = 7) -> dict:
    """Compute + persist daily summaries for every active tank (daily beat)."""
    results = [
        asyncio.run(_compute_and_store(tank_id, days, window_days))
        for tank_id in _tank_ids()
    ]
    return {"tanks_computed": len(results), "days": days, "window_days": window_days}