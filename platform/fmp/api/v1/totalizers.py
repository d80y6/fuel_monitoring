"""Totalizer (secret counter meter) API: read-only hardware audit series."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter
from sqlalchemy import select

from fmp.api.deps import CurrentUser, SessionDep
from fmp.models import StationTotalizer
from fmp.schemas.totalizers import TotalizerPoint

router = APIRouter(prefix="/api/v1/totalizers", tags=["totalizers"])


@router.get("", response_model=list[TotalizerPoint])
async def totalizer_series(
    dispenser_id: uuid.UUID,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 500,
    _: CurrentUser = None,
    session: SessionDep = None,
):
    stmt = select(StationTotalizer).where(StationTotalizer.dispenser_id == dispenser_id)
    if start:
        stmt = stmt.where(StationTotalizer.created_at >= start)
    if end:
        stmt = stmt.where(StationTotalizer.created_at <= end)
    rows = (
        await session.execute(stmt.order_by(StationTotalizer.created_at.desc()).limit(limit))
    ).scalars().all()
    return [
        TotalizerPoint(
            timestamp=r.created_at,
            station_id=r.station_id,
            dispenser_id=r.dispenser_id,
            totalizer_value=r.totalizer_value,
            cumulative_liters=r.cumulative_liters,
            source=r.source,
        )
        for r in rows
    ]