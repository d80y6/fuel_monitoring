"""Storage telemetry API: tank inventory, live status, time-range queries, alarms.

Endpoints
---------
* GET  /api/v1/tanks                    – list tanks (optionally by site)
* GET  /api/v1/tanks/{id}               – single tank
* POST /api/v1/tanks                    – register a tank
* GET  /api/v1/tanks/{id}/recent        – latest N measurements (hypertable read)
* GET  /api/v1/tanks/{id}/range         – time-bucketed series in a window
* GET  /api/v1/tanks/{id}/alarms        – alarm history
* POST /api/v1/tanks/{id}/alarms/{aid}/ack – acknowledge an alarm
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import cast, desc, func, literal, select
from sqlalchemy.dialects.postgresql import INTERVAL

from fmp.api.deps import CurrentUser, PrivilegedUser, SessionDep
from fmp.models import Alarm, Measurement, Tank
from fmp.schemas.tanks import (
    AlarmAckOutcome,
    AlarmSummary,
    TankCreate,
    TankRead,
    TelemetryPoint,
)

router = APIRouter(prefix="/api/v1/tanks", tags=["tanks"])


@router.get("", response_model=list[TankRead])
async def list_tanks(
    site_id: uuid.UUID | None = None,
    session: SessionDep = None,
    _: CurrentUser = None,
):
    stmt = select(Tank).where(Tank.deleted_at.is_(None))
    if site_id:
        stmt = stmt.where(Tank.site_id == site_id)
    rows = (await session.execute(stmt.order_by(Tank.name))).scalars().all()
    return rows


@router.post("", response_model=TankRead, status_code=201)
async def create_tank(
    payload: TankCreate, session: SessionDep = None, _: PrivilegedUser = None
):
    dup = (
        await session.execute(
            select(Tank).where(Tank.sensor_serial_number == payload.sensor_serial_number)
        )
    ).scalar_one_or_none()
    if dup is not None and dup.deleted_at is None:
        raise HTTPException(409, "sensor serial already registered")
    tank = Tank(**payload.model_dump())
    session.add(tank)
    await session.commit()
    await session.refresh(tank)
    return tank


@router.get("/{tank_id}", response_model=TankRead)
async def get_tank(tank_id: uuid.UUID, session: SessionDep = None, _: CurrentUser = None):
    tank = (
        await session.execute(select(Tank).where(Tank.id == tank_id))
    ).scalar_one_or_none()
    if tank is None or tank.deleted_at is not None:
        raise HTTPException(404, "tank not found")
    return tank


@router.get("/{tank_id}/recent", response_model=list[TelemetryPoint])
async def recent_measurements(
    tank_id: uuid.UUID,
    limit: int = Query(default=100, ge=1, le=1000),
    session: SessionDep = None,
    _: CurrentUser = None,
):
    rows = (
        await session.execute(
            select(Measurement)
            .where(Measurement.tank_id == tank_id)
            .order_by(desc(Measurement.timestamp))
            .limit(limit)
        )
    ).scalars().all()
    return [
        TelemetryPoint(
            timestamp=p.timestamp, pressure=p.pressure, temperature=p.temperature,
            level=p.level, volume=p.volume, flow_rate=p.flow_rate,
            gov_volume=p.gov_volume, net_volume=p.net_volume,
            density_at_temperature=p.density_at_temperature,
            fill_percent=p.fill_percent, is_outlier=p.is_outlier,
        )
        for p in reversed(rows)
    ]


@router.get("/{tank_id}/range", response_model=list[TelemetryPoint])
async def range_measurements(
    tank_id: uuid.UUID,
    start: datetime = Query(...),
    end: datetime = Query(...),
    bucket: str = Query(default="5 minutes"),
    session: SessionDep = None,
    _: CurrentUser = None,
):
    """Time-bucketed averages for charting (TimescaleDB time_bucket continuous
    aggregation over 5-minute buckets)."""
    bucket_col = func.time_bucket(cast(literal(bucket), INTERVAL), Measurement.timestamp).label("bucket")
    stmt = (
        select(
            bucket_col,
            func.avg(Measurement.pressure).label("pressure"),
            func.avg(Measurement.temperature).label("temperature"),
            func.avg(Measurement.level).label("level"),
            func.avg(Measurement.volume).label("volume"),
            func.avg(Measurement.gov_volume).label("gov_volume"),
            func.avg(Measurement.net_volume).label("net_volume"),
            func.avg(Measurement.density_at_temperature).label("density_at_temperature"),
            func.max(Measurement.fill_percent).label("fill_percent"),
        )
        .where(
            Measurement.tank_id == tank_id,
            Measurement.timestamp >= start,
            Measurement.timestamp <= end,
        )
        .group_by(bucket_col)
        .order_by(bucket_col)
    )
    rows = (await session.execute(stmt)).all()
    return [
        TelemetryPoint(
            timestamp=r.bucket, pressure=r.pressure, temperature=r.temperature,
            level=r.level, volume=r.volume, gov_volume=r.gov_volume,
            net_volume=r.net_volume, density_at_temperature=r.density_at_temperature,
            fill_percent=r.fill_percent,
        )
        for r in rows
    ]


@router.get("/{tank_id}/alarms", response_model=list[AlarmSummary])
async def tank_alarms(
    tank_id: uuid.UUID,
    open_only: bool = False,
    limit: int = Query(default=50, ge=1, le=500),
    session: SessionDep = None,
    _: CurrentUser = None,
):
    stmt = select(Alarm).where(Alarm.tank_id == tank_id)
    if open_only:
        stmt = stmt.where(Alarm.acknowledged.is_(False))
    rows = (
        await session.execute(stmt.order_by(desc(Alarm.timestamp)).limit(limit))
    ).scalars().all()
    return rows


@router.post("/{tank_id}/alarms/{alarm_id}/ack", response_model=AlarmAckOutcome)
async def acknowledge_alarm(
    tank_id: uuid.UUID,
    alarm_id: uuid.UUID,
    acknowledged_by: uuid.UUID | None = Query(default=None),
    session: SessionDep = None,
    _: PrivilegedUser = None,
):
    alarm = (
        await session.execute(
            select(Alarm).where(Alarm.id == alarm_id, Alarm.tank_id == tank_id)
        )
    ).scalar_one_or_none()
    if alarm is None:
        raise HTTPException(404, "alarm not found")
    alarm.acknowledged = True
    alarm.acknowledged_by = acknowledged_by
    alarm.acknowledged_at = datetime.utcnow()
    await session.commit()
    return AlarmAckOutcome(alarm_id=alarm.id, acknowledged=True)