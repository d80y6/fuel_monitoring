"""Totalizer (secret counter meter) API: read-only hardware audit series."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from fmp.api.deps import CurrentUser, SessionDep
from fmp.core.tenancy import company_id_for_station, tenant_scope
from fmp.models import StationTotalizer
from fmp.schemas.totalizers import TotalizerPoint

router = APIRouter(prefix="/api/v1/totalizers", tags=["totalizers"])


async def _station_id_for_dispenser(session, dispenser_id: uuid.UUID) -> uuid.UUID | None:
    from fmp.models import Dispenser

    row = (
        await session.execute(
            select(Dispenser.station_id).where(Dispenser.id == dispenser_id)
        )
    ).first()
    return row[0] if row else None


@router.get("", response_model=list[TotalizerPoint])
async def totalizer_series(
    dispenser_id: uuid.UUID,
    current: CurrentUser,
    session: SessionDep,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 500,
):
    """Totalizer series for one dispenser, scoped to the caller's tenant."""
    station_id = await _station_id_for_dispenser(session, dispenser_id)
    if station_id is None:
        raise HTTPException(404, "dispenser not found")
    scope = tenant_scope(current)
    if not scope.is_platform:
        company_id = await company_id_for_station(session, station_id)
        if company_id is None or company_id != scope.company_id:
            raise HTTPException(404, "dispenser not found")
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