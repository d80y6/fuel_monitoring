"""Audit event read API (G-116).

Writes go through :mod:`fmp.services.audit` on the mutating endpoints; this
router exposes the history, tenant-scoped, with filters an operator actually
needs: who did what, to which entity, for which tenant, in what window.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from fmp.api.deps import CurrentUser, SessionDep
from fmp.core.tenancy import scope_company_query, tenant_scope
from fmp.models import AuditEvent

router = APIRouter(prefix="/api/v1/audit-events", tags=["audit"])


class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    at: datetime
    actor_id: uuid.UUID | None
    actor_username: str | None
    company_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: str | None
    detail: dict | None


@router.get("", response_model=list[AuditEventRead])
async def list_audit_events(
    current: CurrentUser,
    session: SessionDep,
    company_id: uuid.UUID | None = Query(default=None),
    actor_id: uuid.UUID | None = Query(default=None),
    action: str | None = Query(default=None, max_length=64),
    entity_type: str | None = Query(default=None, max_length=64),
    entity_id: str | None = Query(default=None, max_length=64),
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """Audit history for the caller's tenant, newest first.

    A tenant admin sees its own organization's trail; a platform admin sees
    everything and may narrow to one company. No mutation endpoint exists —
    audit rows are append-only by construction (the table has no update path).
    """
    scope = tenant_scope(current)
    stmt = select(AuditEvent).order_by(AuditEvent.at.desc()).limit(limit).offset(offset)
    stmt = scope_company_query(stmt, AuditEvent.company_id, scope)  # type: ignore[arg-type]

    if scope.is_platform and company_id is not None:
        stmt = stmt.where(AuditEvent.company_id == company_id)
    if actor_id is not None:
        stmt = stmt.where(AuditEvent.actor_id == actor_id)
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    if entity_type:
        stmt = stmt.where(AuditEvent.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditEvent.entity_id == entity_id)
    if start is not None:
        stmt = stmt.where(AuditEvent.at >= start)
    if end is not None:
        stmt = stmt.where(AuditEvent.at <= end)
    return (await session.execute(stmt)).scalars().all()