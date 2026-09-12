"""Consumption analytics API: daily liters + simple-moving-average forecast.

* GET /api/v1/analytics/consumption/{tank_id}  – series + SMA forecast

Mirrors legacy ``tasks/analytics.py`` (daily consumption + forecast). The data
is computed on the fly from raw measurements; the Celery task persists the same
series into ``consumption_summaries`` for offline history.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from fmp.api.deps import CurrentUser, SessionDep
from fmp.core.config import get_settings
from fmp.models import Tank
from fmp.services.analytics.consumption import compute_consumption

settings = get_settings()

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/consumption/{tank_id}")
async def tank_consumption(
    tank_id: uuid.UUID,
    days: int = Query(default=30, ge=1, le=365),
    window_days: int = Query(default=7, ge=1, le=60),
    session: SessionDep = None,
    _: CurrentUser = None,
):
    """Daily consumption (liters) + SMA forecast for one tank."""
    tank = (
        await session.execute(select(Tank).where(Tank.id == tank_id))
    ).scalar_one_or_none()
    if tank is None or tank.deleted_at is not None:
        raise HTTPException(404, "tank not found")
    return await compute_consumption(
        session, tank_id, days=days, window_days=window_days
    )