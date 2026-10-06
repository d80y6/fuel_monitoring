"""Notification channel + rule + delivery-log API.

Three resources, all tenant-scoped:

* ``/api/v1/notification-gateways`` — outbound channels. ``config_json`` is
  **write-only**: reads return masked secrets (G-005).
* ``/api/v1/notification-rules``    — event routing (which target gets told
  about which alarm, over which channel).
* ``/api/v1/notifications/logs``    — delivery history with real provider
  status; nothing here is fabricated.
"""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Body, HTTPException, Query
from sqlalchemy import or_, select

from fmp.api.deps import AdminUser, CurrentUser, PrivilegedUser, SessionDep
from fmp.core.tenancy import TenantScope, scope_or_platform_query, tenant_scope
from fmp.models import Company, NotificationGateway, NotificationLog, NotificationRule
from fmp.schemas.notifications import (
    EventDispatchSummary,
    NotificationGatewayCreate,
    NotificationGatewayRead,
    NotificationGatewayUpdate,
    NotificationLogOut,
    NotificationRuleCreate,
    NotificationRuleRead,
    NotificationRuleUpdate,
)
from fmp.services import audit as audit_log
from fmp.services.notifications.rules import default_test_text, dispatch_event, send_test_message
from fmp.services.notifications.secrets import mask_config, merge_config

router = APIRouter(tags=["notifications"])

# ---------------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------------


def _to_read(gateway: NotificationGateway) -> NotificationGatewayRead:
    """Serialize a channel with every credential masked."""
    stored = json.loads(gateway.config_json) if gateway.config_json else {}
    return NotificationGatewayRead(
        id=gateway.id,
        name=gateway.name,
        type=gateway.type,
        config_json=mask_config(stored, gateway.type),
        is_active=gateway.is_active,
        priority=gateway.priority,
        company_id=gateway.company_id,
        created_at=gateway.created_at,
    )


async def _load_channel(
    session, gateway_id: uuid.UUID, scope: TenantScope, *, for_write: bool = False
) -> NotificationGateway:
    """Fetch a channel the caller may see; platform-wide rows are read-only for tenants."""
    stmt = scope_or_platform_query(
        select(NotificationGateway).where(NotificationGateway.id == gateway_id),  # type: ignore[arg-type]
        NotificationGateway.company_id,
        scope,
    )
    gateway = (await session.execute(stmt)).scalar_one_or_none()
    if gateway is None:
        raise HTTPException(404, "gateway not found")
    if for_write and not scope.is_platform and gateway.company_id is None:
        # Platform channel: tenants may use it, never reconfigure it.
        raise HTTPException(403, "platform-wide channels can only be managed by platform admins")
    return gateway


@router.get("/api/v1/notification-gateways", response_model=list[NotificationGatewayRead])
async def list_gateways(
    current: CurrentUser,
    session: SessionDep,
    type: str | None = None,
):
    scope = tenant_scope(current)
    stmt = select(NotificationGateway).order_by(
        NotificationGateway.is_active.desc(), NotificationGateway.priority.asc()
    )
    stmt = scope_or_platform_query(stmt, NotificationGateway.company_id, scope)  # type: ignore[arg-type]
    if type:
        stmt = stmt.where(NotificationGateway.type == type)
    rows = (await session.execute(stmt)).scalars().all()
    return [_to_read(g) for g in rows]


@router.post(
    "/api/v1/notification-gateways", response_model=NotificationGatewayRead, status_code=201
)
async def create_gateway(
    payload: NotificationGatewayCreate, current: PrivilegedUser, session: SessionDep
):
    scope = tenant_scope(current)
    dup = (
        await session.execute(
            select(NotificationGateway).where(NotificationGateway.name == payload.name)
        )
    ).scalar_one_or_none()
    if dup is not None:
        raise HTTPException(409, "gateway name already exists")
    # Only platform admins may create platform-wide (NULL company) channels.
    company_id = None if scope.is_platform else scope.company_id
    if company_id is None and not scope.is_platform:
        raise HTTPException(403, "user is not assigned to a company")
    gateway = NotificationGateway(
        name=payload.name,
        type=payload.type,
        company_id=company_id,
        config_json=json.dumps(payload.config_json),
        is_active=payload.is_active,
        priority=payload.priority,
    )
    session.add(gateway)
    await session.flush()
    audit_log.record(
        session, actor=current, action="notification_gateway.create",
        entity_type="notification_gateway", entity_id=gateway.id, company_id=company_id,
        detail={"name": gateway.name, "type": gateway.type},
    )
    await session.commit()
    await session.refresh(gateway)
    return _to_read(gateway)


@router.get(
    "/api/v1/notification-gateways/{gateway_id}", response_model=NotificationGatewayRead
)
async def get_gateway(gateway_id: uuid.UUID, current: CurrentUser, session: SessionDep):
    return _to_read(await _load_channel(session, gateway_id, tenant_scope(current)))


@router.patch(
    "/api/v1/notification-gateways/{gateway_id}", response_model=NotificationGatewayRead
)
async def update_gateway(
    gateway_id: uuid.UUID,
    payload: NotificationGatewayUpdate,
    current: PrivilegedUser,
    session: SessionDep,
):
    scope = tenant_scope(current)
    gateway = await _load_channel(session, gateway_id, scope, for_write=True)
    data = payload.model_dump(exclude_unset=True)
    if "config_json" in data and data["config_json"] is not None:
        stored = json.loads(gateway.config_json) if gateway.config_json else {}
        gateway.config_json = json.dumps(merge_config(stored, data.pop("config_json"), gateway.type))
    for field, value in data.items():
        setattr(gateway, field, value)
    audit_log.record(
        session, actor=current, action="notification_gateway.update",
        entity_type="notification_gateway", entity_id=gateway.id,
        company_id=gateway.company_id, detail={"changed": sorted(payload.model_dump(exclude_unset=True).keys())},
    )
    await session.commit()
    await session.refresh(gateway)
    return _to_read(gateway)


@router.delete("/api/v1/notification-gateways/{gateway_id}", status_code=204)
async def delete_gateway(gateway_id: uuid.UUID, current: PrivilegedUser, session: SessionDep):
    scope = tenant_scope(current)
    gateway = await _load_channel(session, gateway_id, scope, for_write=True)
    if not scope.is_platform and gateway.company_id != scope.company_id:
        raise HTTPException(403, "cannot delete another tenant's channel")
    audit_log.record(
        session, actor=current, action="notification_gateway.delete",
        entity_type="notification_gateway", entity_id=gateway.id, company_id=gateway.company_id,
        detail={"name": gateway.name},
    )
    await session.delete(gateway)
    await session.commit()


@router.post("/api/v1/notification-gateways/{gateway_id}/test")
async def test_gateway(
    gateway_id: uuid.UUID,
    current: PrivilegedUser,
    session: SessionDep,
    recipient: str = Body(embed=True),
    message: str | None = Body(default=None, embed=True),
) -> dict:
    """Send a real test message through the channel and record the delivery.

    Returns the provider's own message id on success; a provider error surfaces
    as a 502 with the provider message. Nothing is reported as sent unless the
    provider call actually returned.
    """
    scope = tenant_scope(current)
    gateway = await _load_channel(session, gateway_id, scope, for_write=True)
    if not gateway.is_active:
        raise HTTPException(400, "channel is inactive")
    text = message or default_test_text()
    try:
        provider_id = await send_test_message(
            session, gateway, recipient, text, gateway.company_id
        )
    except Exception as exc:  # noqa: BLE001 - report the provider error verbatim
        audit_log.record(
            session, actor=current, action="notification_gateway.test_failed",
            entity_type="notification_gateway", entity_id=gateway.id,
            company_id=gateway.company_id, detail={"recipient": recipient, "error": f"{exc}"},
        )
        await session.commit()
        raise HTTPException(502, f"provider rejected the test message: {exc}") from exc
    audit_log.record(
        session, actor=current, action="notification_gateway.test",
        entity_type="notification_gateway", entity_id=gateway.id,
        company_id=gateway.company_id, detail={"recipient": recipient},
    )
    await session.commit()
    return {"status": "SENT", "provider_message_id": provider_id, "recipient": recipient}


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


async def _load_rule(session, rule_id: uuid.UUID, scope: TenantScope, *, for_write=False):
    stmt = scope_or_platform_query(
        select(NotificationRule).where(NotificationRule.id == rule_id),  # type: ignore[arg-type]
        NotificationRule.company_id,
        scope,
    )
    rule = (await session.execute(stmt)).scalar_one_or_none()
    if rule is None:
        raise HTTPException(404, "notification rule not found")
    if for_write and not scope.is_platform and rule.company_id is None:
        raise HTTPException(403, "platform-wide rules can only be managed by platform admins")
    return rule


@router.get("/api/v1/notification-rules", response_model=list[NotificationRuleRead])
async def list_rules(current: CurrentUser, session: SessionDep, site_id: uuid.UUID | None = None):
    scope = tenant_scope(current)
    stmt = scope_or_platform_query(
        select(NotificationRule).order_by(NotificationRule.created_at.desc()),  # type: ignore[arg-type]
        NotificationRule.company_id,
        scope,
    )
    if site_id:
        stmt = stmt.where(or_(NotificationRule.site_id == site_id, NotificationRule.site_id.is_(None)))
    rows = (await session.execute(stmt)).scalars().all()
    return rows


@router.post("/api/v1/notification-rules", response_model=NotificationRuleRead, status_code=201)
async def create_rule(
    payload: NotificationRuleCreate, current: PrivilegedUser, session: SessionDep
):
    scope = tenant_scope(current)
    company_id = None if scope.is_platform else scope.company_id
    if company_id is None and not scope.is_platform:
        raise HTTPException(403, "user is not assigned to a company")
    if payload.site_id is not None:
        await _require_site_in_scope(session, payload.site_id, scope)
    rule = NotificationRule(**payload.model_dump(exclude={"company_id"}), company_id=company_id)
    session.add(rule)
    await session.flush()
    audit_log.record(
        session, actor=current, action="notification_rule.create",
        entity_type="notification_rule", entity_id=rule.id, company_id=company_id,
        detail={"name": rule.name, "channel": rule.channel, "min_level": rule.min_level},
    )
    await session.commit()
    await session.refresh(rule)
    return rule


@router.patch("/api/v1/notification-rules/{rule_id}", response_model=NotificationRuleRead)
async def update_rule(
    rule_id: uuid.UUID,
    payload: NotificationRuleUpdate,
    current: PrivilegedUser,
    session: SessionDep,
):
    scope = tenant_scope(current)
    rule = await _load_rule(session, rule_id, scope, for_write=True)
    data = payload.model_dump(exclude_unset=True)
    if "site_id" in data and data["site_id"] is not None:
        await _require_site_in_scope(session, data["site_id"], scope)
    for field, value in data.items():
        setattr(rule, field, value)
    audit_log.record(
        session, actor=current, action="notification_rule.update",
        entity_type="notification_rule", entity_id=rule.id, company_id=rule.company_id,
        detail={"changed": sorted(data.keys())},
    )
    await session.commit()
    await session.refresh(rule)
    return rule


@router.delete("/api/v1/notification-rules/{rule_id}", status_code=204)
async def delete_rule(rule_id: uuid.UUID, current: PrivilegedUser, session: SessionDep):
    scope = tenant_scope(current)
    rule = await _load_rule(session, rule_id, scope, for_write=True)
    audit_log.record(
        session, actor=current, action="notification_rule.delete",
        entity_type="notification_rule", entity_id=rule.id, company_id=rule.company_id,
        detail={"name": rule.name},
    )
    await session.delete(rule)
    await session.commit()


async def _require_site_in_scope(session, site_id: uuid.UUID, scope: TenantScope) -> None:
    from fmp.models import Site

    site = (
        await session.execute(
            select(Site).where(Site.id == site_id, Site.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if site is None:
        raise HTTPException(404, "site not found")
    if not scope.is_platform and site.company_id != scope.company_id:
        raise HTTPException(404, "site not found")


# ---------------------------------------------------------------------------
# Delivery history + on-demand event test
# ---------------------------------------------------------------------------


@router.get("/api/v1/notifications/logs", response_model=list[NotificationLogOut])
async def list_logs(
    current: CurrentUser,
    session: SessionDep,
    status: str | None = None,
    channel: str | None = None,
    event_type: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
):
    scope = tenant_scope(current)
    stmt = select(NotificationLog).order_by(NotificationLog.created_at.desc()).limit(limit)
    if not scope.is_platform:
        stmt = stmt.where(
            or_(
                NotificationLog.company_id == scope.company_id,
                NotificationLog.company_id.is_(None),
            )
        )
    if status:
        stmt = stmt.where(NotificationLog.status == status)
    if channel:
        stmt = stmt.where(NotificationLog.channel == channel)
    if event_type:
        stmt = stmt.where(NotificationLog.event_type == event_type)
    rows = (await session.execute(stmt)).scalars().all()
    return rows


@router.post("/api/v1/notifications/test-dispatch", response_model=EventDispatchSummary)
async def test_rule_dispatch(
    current: AdminUser,
    session: SessionDep,
    level: str = Query(default="CRITICAL", pattern="^(WARNING|CRITICAL)$"),
    company_id: uuid.UUID | None = Query(default=None),
) -> EventDispatchSummary:
    """Dry-run the rule engine end-to-end against real gateways.

    Platform-admin only: it exercises the tenant-scoped rule matching so an
    operator can confirm alarm notifications actually deliver. Deliveries are
    logged as ``event_type='test'`` in the same history as real alarms.
    """
    if company_id is not None:
        company = (
            await session.execute(
                select(Company).where(Company.id == company_id, Company.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
        if company is None:
            raise HTTPException(404, "company not found")
    return await dispatch_event(
        session,
        event_type="alarm",
        level=level,
        company_id=company_id,
        context={
            "tank": "TEST TANK",
            "site": "TEST SITE",
            "level": level,
            "message": "Test alarm notification from the fuel platform",
            "event_ref": "test",
        },
        default_message="[TEST] Fuel platform alarm {level} on {tank} at {site}: {message}",
    )
