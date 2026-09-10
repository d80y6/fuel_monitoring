"""IoT gateway CRUD + command API."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from fmp.api.deps import CurrentUser, PrivilegedUser, SessionDep
from fmp.models import IoTGateway, Tank
from fmp.schemas.iot import IoTGatewayCreate, IoTGatewayRead, IoTGatewayUpdate

router = APIRouter(prefix="/api/v1/iot-gateways", tags=["iot-gateways"])


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
    payload: IoTGatewayCreate, _: PrivilegedUser, session: SessionDep
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
    _: PrivilegedUser,
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
        for t in tanks:
            t.gateway_id = gateway.id
        if tanks:
            gateway.is_active = True
    await session.commit()
    await session.refresh(gateway)
    return _to_read(gateway, await _tank_ids(session, gateway))
