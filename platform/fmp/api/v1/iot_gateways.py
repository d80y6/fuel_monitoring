"""IoT gateway CRUD + command API, tenant-scoped.

A gateway is a physical radio device that may legitimately serve tanks belonging
to several organizations, so it cannot simply carry a single ``company_id``.
Visibility is therefore derived:

* a platform operator sees every gateway;
* a tenant sees the gateways it *owns* (``company_id`` set) **and** the
  gateways that carry at least one of its tanks.

Mutations are stricter than reads: attaching or detaching a tank is always
restricted to tanks inside the caller's own organization, and only a platform
admin may move a tank between organizations. Without that, a platform-level
``PATCH`` would silently detach another tenant's tanks (audit finding L4).
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import exists, select

from fmp.api.deps import CurrentUser, SessionDep, require_roles
from fmp.core.redis import RedisClient
from fmp.core.tenancy import TenantScope, tenant_scope
from fmp.ingestion.relay import enqueue_command
from fmp.models import GatewayCommand, IoTGateway, Site, Tank, User
from fmp.schemas.iot import (
    IoTCommandCreate,
    IoTCommandIssue,
    IoTCommandRead,
    IoTGatewayCreate,
    IoTGatewayRead,
    IoTGatewayUpdate,
)

router = APIRouter(prefix="/api/v1/iot-gateways", tags=["iot-gateways"])

AdminUser = Annotated[User, Depends(require_roles("admin"))]


def _tanks_of_company(subquery):
    """Select of tank ids belonging to ``company_id``."""
    return (
        select(Tank.id)
        .join(Site, Site.id == Tank.site_id)
        .where(Site.company_id == subquery)
    )


async def _visible_gateways_stmt(session, scope: TenantScope):
    """Gateways the caller may see."""
    stmt = select(IoTGateway)
    if scope.is_platform:
        return stmt
    own_tank_ids = _tanks_of_company(scope.company_id).scalar_subquery()
    carries_my_tank = exists(
        select(1).where(Tank.gateway_id == IoTGateway.id, Tank.id.in_(own_tank_ids))
    )
    return stmt.where(
        (IoTGateway.company_id == scope.company_id) | carries_my_tank
    )


async def _get_gateway(session, gateway_id: uuid.UUID, scope: TenantScope) -> IoTGateway:
    """Load a gateway the caller may see, else 404 (never reveal that it exists)."""
    stmt = (await _visible_gateways_stmt(session, scope)).where(IoTGateway.id == gateway_id)
    gateway = (await session.execute(stmt)).scalar_one_or_none()
    if gateway is None:
        raise HTTPException(404, "gateway not found")
    return gateway


async def _tank_ids(session, gateway, scope: TenantScope) -> list[uuid.UUID]:
    """Attached tank ids, restricted to the caller's own organization."""
    stmt = select(Tank.id).where(Tank.gateway_id == gateway.id)
    if not scope.is_platform:
        stmt = stmt.where(Tank.id.in_(_tanks_of_company(scope.company_id).scalar_subquery()))
    return list((await session.execute(stmt)).scalars().all())


async def _require_mutable_tank(session, tank_id: uuid.UUID, scope: TenantScope) -> Tank:
    """A tank may only be attached/detached by someone who owns its organization."""
    stmt = select(Tank).where(Tank.id == tank_id, Tank.deleted_at.is_(None))
    tank = (await session.execute(stmt)).scalar_one_or_none()
    if tank is None:
        raise HTTPException(404, "tank not found")
    if scope.is_platform:
        return tank
    company_id = (
        await session.execute(select(Site.company_id).where(Site.id == tank.site_id))
    ).first()
    if not company_id or company_id[0] != scope.company_id:
        raise HTTPException(404, "tank not found")
    return tank


def _to_read(gateway: IoTGateway, tank_ids: list[uuid.UUID]) -> IoTGatewayRead:
    return IoTGatewayRead(
        id=gateway.id,
        gateway_mac=gateway.gateway_mac,
        name=gateway.name,
        firmware_version=gateway.firmware_version,
        last_seen=gateway.last_seen,
        connection_status=gateway.connection_status,
        is_active=gateway.is_active,
        company_id=gateway.company_id,
        tank_ids=tank_ids,
        created_at=gateway.created_at,
    )


@router.get("", response_model=list[IoTGatewayRead])
async def list_gateways(
    current: CurrentUser,
    session: SessionDep,
    active: bool | None = Query(default=None),
):
    """List gateways visible to the caller, each with only its own tanks attached."""
    scope = tenant_scope(current)
    stmt = (await _visible_gateways_stmt(session, scope)).order_by(
        IoTGateway.created_at.desc()
    )
    if active is not None:
        stmt = stmt.where(IoTGateway.is_active.is_(active))
    rows = (await session.execute(stmt)).scalars().all()
    return [_to_read(g, await _tank_ids(session, g, scope)) for g in rows]


@router.post("", response_model=IoTGatewayRead, status_code=201)
async def create_gateway(payload: IoTGatewayCreate, current: AdminUser, session: SessionDep):
    existing = (
        await session.execute(
            select(IoTGateway).where(IoTGateway.gateway_mac == payload.gateway_mac)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(409, "gateway_mac already registered")
    gateway = IoTGateway(
        gateway_mac=payload.gateway_mac,
        name=payload.name or payload.gateway_mac,
        firmware_version=payload.firmware_version,
        # A platform admin creating a gateway owns it at the platform level;
        # a tenant-scoped admin is a platform admin by definition here, so the
        # owner is explicit rather than implied.
        company_id=payload.company_id,
        is_active=False,
    )
    session.add(gateway)
    await session.commit()
    await session.refresh(gateway)
    return _to_read(gateway, [])


@router.get("/{gateway_id}", response_model=IoTGatewayRead)
async def get_gateway(gateway_id: uuid.UUID, current: CurrentUser, session: SessionDep):
    scope = tenant_scope(current)
    gateway = await _get_gateway(session, gateway_id, scope)
    return _to_read(gateway, await _tank_ids(session, gateway, scope))


@router.patch("/{gateway_id}", response_model=IoTGatewayRead)
async def update_gateway(
    gateway_id: uuid.UUID,
    payload: IoTGatewayUpdate,
    current: AdminUser,
    session: SessionDep,
):
    """Update gateway metadata and re-bind tanks.

    Detaching only ever touches tanks the caller owns: re-binding is a
    destructive cross-tenant operation if it silently unpicks another tenant's
    hardware (audit finding L4).
    """
    scope = tenant_scope(current)
    gateway = await _get_gateway(session, gateway_id, scope)
    data = payload.model_dump(exclude_unset=True)
    tank_ids = data.pop("tank_ids", None)

    for field, value in data.items():
        setattr(gateway, field, value)

    if tank_ids is not None:
        requested = list(dict.fromkeys(tank_ids))  # de-duplicate, preserve order
        tanks = [await _require_mutable_tank(session, tid, scope) for tid in requested]
        current_tanks = (
            await session.execute(select(Tank).where(Tank.gateway_id == gateway.id))
        ).scalars().all()
        for tank in current_tanks:
            await _require_mutable_tank(session, tank.id, scope)
            tank.gateway_id = None
        for tank in tanks:
            tank.gateway_id = gateway.id
        gateway.is_active = bool(tanks) or gateway.is_active

    await session.commit()
    await session.refresh(gateway)
    return _to_read(gateway, await _tank_ids(session, gateway, scope))


@router.post("/{gateway_id}/commands", response_model=IoTCommandIssue, status_code=202)
async def issue_command(
    gateway_id: uuid.UUID,
    payload: IoTCommandCreate,
    current: AdminUser,
    session: SessionDep,
):
    scope = tenant_scope(current)
    gateway = await _get_gateway(session, gateway_id, scope)
    if not gateway.is_active:
        raise HTTPException(409, "gateway is not active — link tanks first")
    command = GatewayCommand(
        gateway_id=gateway.id,
        command_type=payload.command_type,
        payload_json=payload.payload,
        status="pending",
        attempts=0,
        max_attempts=3,
    )
    session.add(command)
    await session.commit()
    await session.refresh(command)

    redis = RedisClient()
    try:
        await enqueue_command(
            redis.client,
            command_id=str(command.command_id),
            gateway_mac=gateway.gateway_mac,
            command_type=payload.command_type,
            payload=payload.payload,
        )
    finally:
        await redis.client.aclose()
    return IoTCommandIssue(command_id=command.command_id, status="pending")


@router.get("/{gateway_id}/commands", response_model=list[IoTCommandRead])
async def list_commands(
    gateway_id: uuid.UUID,
    current: CurrentUser,
    session: SessionDep,
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
):
    """Command history for a visible gateway."""
    scope = tenant_scope(current)
    await _get_gateway(session, gateway_id, scope)
    stmt = (
        select(GatewayCommand)
        .where(GatewayCommand.gateway_id == gateway_id)
        .order_by(GatewayCommand.created_at.desc())
        .limit(limit)
    )
    if status:
        stmt = stmt.where(GatewayCommand.status == status)
    return list((await session.execute(stmt)).scalars().all())