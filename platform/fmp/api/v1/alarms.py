"""Cross-tank alarm API (tenant-scoped).

Single, paginated surface for operations consoles — replaces the client-side
N+1 fan-out over ``/api/v1/tanks/{id}/alarms``.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from fmp.api.deps import CurrentUser, PrivilegedUser, SessionDep
from fmp.models import Alarm, Site, Tank
from fmp.schemas.tanks import AlarmAckOutcome, AlarmSummary
from fmp.services import audit as audit_log

router = APIRouter(prefix="/api/v1/alarms", tags=["alarms"])


def _scoped_stmt(caller):
    stmt = (
        select(Alarm, Tank, Site)
        .join(Tank, Tank.id == Alarm.tank_id)
        .join(Site, Site.id == Tank.site_id)
        .where(Tank.deleted_at.is_(None))
    )
    if caller.role != "admin":
        stmt = stmt.where(Site.company_id == caller.company_id)
    return stmt


def _to_summary(alarm: Alarm, tank: Tank, site: Site) -> AlarmSummary:
    return AlarmSummary(
        id=alarm.id,
        tank_id=alarm.tank_id,
        timestamp=alarm.timestamp,
        type=alarm.type,
        level=alarm.level,
        message=alarm.message,
        value=alarm.value,
        state=alarm.state,
        resolved_at=alarm.resolved_at,
        resolved_message=alarm.resolved_message,
        acknowledged=alarm.acknowledged,
        acknowledged_at=alarm.acknowledged_at,
        tank_name=tank.name,
        site_id=site.id,
        company_id=site.company_id,
    )


@router.get("", response_model=list[AlarmSummary])
async def list_alarms(
    current: CurrentUser,
    session: SessionDep,
    state: str | None = Query(default=None, pattern="^(active|acknowledged|resolved)$"),
    type: str | None = Query(default=None),
    site_id: uuid.UUID | None = Query(default=None),
    tank_id: uuid.UUID | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    stmt = _scoped_stmt(current)
    if state:
        stmt = stmt.where(Alarm.state == state)
    if type:
        stmt = stmt.where(Alarm.type == type)
    if site_id:
        stmt = stmt.where(Site.id == site_id)
    if tank_id:
        stmt = stmt.where(Alarm.tank_id == tank_id)
    if since:
        stmt = stmt.where(Alarm.timestamp >= since)
    if until:
        stmt = stmt.where(Alarm.timestamp <= until)
    rows = (
        await session.execute(
            stmt.order_by(desc(Alarm.timestamp)).offset(offset).limit(limit)
        )
    ).all()
    return [_to_summary(a, t, s) for a, t, s in rows]


@router.post("/{alarm_id}/ack", response_model=AlarmAckOutcome)
async def ack_alarm(
    alarm_id: uuid.UUID,
    current: PrivilegedUser,
    session: SessionDep,
):
    alarm, _tank, _site = await _load_scoped(session, alarm_id, current)
    alarm.acknowledged = True
    alarm.acknowledged_by = current.id
    alarm.acknowledged_at = datetime.now(UTC)
    if alarm.state == "active":
        alarm.state = "acknowledged"
    audit_log.record(
        session, actor=current, action="alarm.ack", entity_type="alarm", entity_id=alarm.id,
        company_id=_site.company_id,
    )
    await session.commit()
    return AlarmAckOutcome(alarm_id=alarm.id, acknowledged=True)


@router.post("/{alarm_id}/resolve", response_model=AlarmSummary)
async def resolve_alarm(
    alarm_id: uuid.UUID,
    current: PrivilegedUser,
    session: SessionDep,
    message: str | None = Query(default=None, max_length=2000),
):
    alarm, tank, site = await _load_scoped(session, alarm_id, current)
    alarm.state = "resolved"
    alarm.resolved_at = datetime.now(UTC)
    alarm.resolved_message = message or f"resolved manually by {current.username}"
    alarm.acknowledged = True
    audit_log.record(
        session, actor=current, action="alarm.resolve", entity_type="alarm",
        entity_id=alarm.id, detail={"message": alarm.resolved_message},
    )
    await session.commit()
    return _to_summary(alarm, tank, site)


async def _load_scoped(
    session: AsyncSession, alarm_id: uuid.UUID, caller
) -> tuple[Alarm, Tank, Site]:
    row = (
        await session.execute(_scoped_stmt(caller).where(Alarm.id == alarm_id))
    ).first()
    if row is None:
        raise HTTPException(404, "alarm not found")
    return row
