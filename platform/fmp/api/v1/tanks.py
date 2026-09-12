"""Storage telemetry API: tank inventory, live status, time-range queries, alarms.

Endpoints
---------
* GET  /api/v1/tanks                    – list tanks (optionally by site)
* GET  /api/v1/tanks/{id}               – single tank
* POST /api/v1/tanks                    – register a tank
* GET  /api/v1/tanks/{id}/recent        – latest N measurements (hypertable read)
* GET  /api/v1/tanks/{id}/range         – time-bucketed series in a window
* GET  /api/v1/tanks/{id}/export        – streamed CSV download for a window
* GET  /api/v1/tanks/{id}/alarms        – alarm history
* POST /api/v1/tanks/{id}/alarms/{aid}/ack – acknowledge an alarm
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import cast, desc, func, literal, select, text
from sqlalchemy.dialects.postgresql import INTERVAL

from fmp.api.deps import CurrentUser, PrivilegedUser, SessionDep
from fmp.core.config import get_settings
from fmp.ingestion.tsdb_policies import choose_cagg
from fmp.models import Alarm, Measurement, Tank
from fmp.schemas.tanks import (
    AlarmAckOutcome,
    AlarmSummary,
    TankCreate,
    TankRead,
    TelemetryPoint,
)

settings = get_settings()

router = APIRouter(prefix="/api/v1/tanks", tags=["tanks"])

CSV_HEADER = (
    "timestamp,tank_id,pressure,temperature,level,volume,flow_rate,"
    "gov_volume,net_volume,density_at_temperature,fill_percent,status,is_outlier"
)


def _csv_fmt(value):
    return f"{value:g}" if value is not None else ""


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
    """Time-bucketed averages for charting.

    Hourly-and-coarser buckets spanning at least two aggregate windows read the
    materialized ``measurements_hourly`` / ``measurements_daily`` continuous
    aggregates instead of scanning raw rows; finer buckets stay on the
    hypertable (``time_bucket`` over the live table).
    """
    cagg = choose_cagg(bucket, (end - start).total_seconds())
    if cagg is not None:
        rows = (await session.execute(text(
            f"SELECT bucket AS timestamp, pressure, temperature, level, volume, "
            f"gov_volume, net_volume, density_at_temperature, fill_percent "
            f"FROM {cagg} "
            f"WHERE tank_id = :tid AND bucket >= :start AND bucket <= :end "
            f"ORDER BY bucket"
        ), {"tid": tank_id, "start": start, "end": end})).all()
    else:
        bucket_col = func.time_bucket(cast(literal(bucket), INTERVAL), Measurement.timestamp).label("timestamp")
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
            timestamp=r.timestamp, pressure=r.pressure, temperature=r.temperature,
            level=r.level, volume=r.volume, gov_volume=r.gov_volume,
            net_volume=r.net_volume, density_at_temperature=r.density_at_temperature,
            fill_percent=r.fill_percent,
        )
        for r in rows
    ]


@router.get("/{tank_id}/export")
async def export_measurements(
    tank_id: uuid.UUID,
    start: datetime = Query(...),
    end: datetime = Query(...),
    batch_size: int = Query(default=settings.CSV_EXPORT_BATCH_SIZE, ge=100, le=10000),
    session: SessionDep = None,
    _: CurrentUser = None,
):
    """Stream raw measurements as CSV, batched in server-side pages.

    The response streams rows in ``batch_size`` keyset chunks so arbitrarily long
    windows never load into memory (parity with the legacy 1000-row batching).
    """
    tank = (
        await session.execute(select(Tank).where(Tank.id == tank_id))
    ).scalar_one_or_none()
    if tank is None or tank.deleted_at is not None:
        raise HTTPException(404, "tank not found")

    from fmp.core.database import async_session_factory

    async def stream():
        yield f"{CSV_HEADER}\n"
        async with async_session_factory() as session:
            cursor = start
            while cursor <= end:
                chunk = (
                    await session.execute(
                        select(Measurement)
                        .where(
                            Measurement.tank_id == tank_id,
                            Measurement.timestamp > cursor,
                            Measurement.timestamp <= end,
                        )
                        .order_by(Measurement.timestamp)
                        .limit(batch_size)
                    )
                ).scalars().all()
                if not chunk:
                    break
                for m in chunk:
                    yield (
                        f"{m.timestamp.isoformat()},{m.tank_id},"
                        f"{_csv_fmt(m.pressure)},{_csv_fmt(m.temperature)},"
                        f"{_csv_fmt(m.level)},{_csv_fmt(m.volume)},"
                        f"{_csv_fmt(m.flow_rate)},{_csv_fmt(m.gov_volume)},"
                        f"{_csv_fmt(m.net_volume)},{_csv_fmt(m.density_at_temperature)},"
                        f"{_csv_fmt(m.fill_percent)},{m.status},{int(bool(m.is_outlier))}\n"
                    )
                cursor = chunk[-1].timestamp

    filename = f"tank-{tank_id}-{start.date().isoformat()}-to-{end.date().isoformat()}.csv"
    return StreamingResponse(
        stream(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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