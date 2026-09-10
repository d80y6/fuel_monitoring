"""IoT gateway CRUD + command API."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from fmp.api.deps import CurrentUser, SessionDep, require_roles
from fmp.core.redis import RedisClient
from fmp.ingestion.relay import enqueue_command
from fmp.models import GatewayCommand, IoTGateway, Tank, User
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


async def _get_gateway(session, gateway_id) -> IoTGateway:
    gateway = (
        await session.execute(select(IoTGateway).where(IoTGateway.id == gateway_id))
    ).scalar_one_or_none()
    if gateway is None:
        raise HTTPException(404, "gateway not found")
    return gateway


async def _tank_ids(session, gateway) -> list[uuid.UUID]:
    rows = (await session.execute(select(Tank.id).where(Tank.gateway_id == gateway.id))).scalars().all()
    return list(rows)


def _to_read(gateway: IoTGateway, tank_ids: list[uuid.UUID]) -> IoTGatewayRead:
    return IoTGatewayRead(
        id=gateway.id,
        gateway_mac=gateway.gateway_mac,
        name=gateway.name,
        firmware_version=gateway.firmware_version,
        last_seen=gateway.last_seen,
        connection_status=gateway.connection_status,
        is_active=gateway.is_active,
        tank_ids=tank_ids,
        created_at=gateway.created_at,
    )


@router.get("", response_model=list[IoTGatewayRead])
async def list_gateways(
    active: bool | None = None,
    _: CurrentUser = None,
    session: SessionDep = None,
):
    stmt = select(IoTGateway).order_by(IoTGateway.created_at.desc())
    if active is not None:
        stmt = stmt.where(IoTGateway.is_active.is_(active))
    rows = (await session.execute(stmt)).scalars().all()
    return [_to_read(g, []) for g in rows]


@router.post("", response_model=IoTGatewayRead, status_code=201)
async def create_gateway(
    payload: IoTGatewayCreate, _: AdminUser, session: SessionDep
):
    existing = (
        await session.execute(select(IoTGateway).where(IoTGateway.gateway_mac == payload.gateway_mac))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(409, "gateway_mac already registered")
    gateway = IoTGateway(
        gateway_mac=payload.gateway_mac,
        name=payload.name or payload.gateway_mac,
        firmware_version=payload.firmware_version,
        is_active=False,
    )
    session.add(gateway)
    await session.commit()
    await session.refresh(gateway)
    return _to_read(gateway, [])


@router.get("/{gateway_id}", response_model=IoTGatewayRead)
async def get_gateway(gateway_id: uuid.UUID, _: CurrentUser, session: SessionDep):
    gateway = await _get_gateway(session, gateway_id)
    return _to_read(gateway, await _tank_ids(session, gateway))


@router.patch("/{gateway_id}", response_model=IoTGatewayRead)
async def update_gateway(
    gateway_id: uuid.UUID,
    payload: IoTGatewayUpdate,
    _: AdminUser,
    session: SessionDep,
):
    gateway = await _get_gateway(session, gateway_id)
    data = payload.model_dump(exclude_unset=True)
    tank_ids = data.pop("tank_ids", None)
    for field, value in data.items():
        setattr(gateway, field, value)
    if tank_ids is not None:
        tanks = (
            await session.execute(select(Tank).where(Tank.id.in_(tank_ids)))
        ).scalars().all()
        if len(tanks) != len(set(tank_ids)):
            raise HTTPException(404, "one or more tanks not found")
        current = (
            await session.execute(select(Tank).where(Tank.gateway_id == gateway.id))
        ).scalars().all()
        for t in current:
            t.gateway_id = None
        for t in tanks:
            t.gateway_id = gateway.id
        if tanks:
            gateway.is_active = True
    await session.commit()
    await session.refresh(gateway)
    return _to_read(gateway, await _tank_ids(session, gateway))


@router.post("/{gateway_id}/commands", response_model=IoTCommandIssue, status_code=202)
async def issue_command(
    gateway_id: uuid.UUID,
    payload: IoTCommandCreate,
    _: AdminUser,
    session: SessionDep,
):
    gateway = await _get_gateway(session, gateway_id)
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
            command_type=command.command_type,
            payload=payload.payload,
        )
    except Exception:
        await redis.client.aclose()
        raise
    await redis.client.aclose()
    return IoTCommandIssue(command_id=command.command_id, status="pending")


@router.get("/{gateway_id}/commands", response_model=list[IoTCommandRead])
async def list_commands(
    gateway_id: uuid.UUID,
    status: str | None = None,
    limit: int = 50,
    _: CurrentUser = None,
    session: SessionDep = None,
):
    await _get_gateway(session, gateway_id)
    stmt = (
        select(GatewayCommand)
        .where(GatewayCommand.gateway_id == gateway_id)
        .order_by(GatewayCommand.created_at.desc())
        .limit(min(limit, 500))
    )
    if status:
        stmt = stmt.where(GatewayCommand.status == status)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)
