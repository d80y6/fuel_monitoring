"""Notification gateway CRUD API."""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from fmp.api.deps import CurrentUser, PrivilegedUser, SessionDep
from fmp.models import NotificationGateway
from fmp.schemas.notifications import (
    NotificationGatewayCreate,
    NotificationGatewayRead,
    NotificationGatewayUpdate,
)

router = APIRouter(prefix="/api/v1/notification-gateways", tags=["notification-gateways"])


def _to_read(gateway: NotificationGateway) -> NotificationGatewayRead:
    return NotificationGatewayRead(
        id=gateway.id,
        name=gateway.name,
        type=gateway.type,
        config_json=json.loads(gateway.config_json) if gateway.config_json else {},
        is_active=gateway.is_active,
        priority=gateway.priority,
        created_at=gateway.created_at,
    )


@router.get("", response_model=list[NotificationGatewayRead])
async def list_gateways(
    type: str | None = None,
    _: CurrentUser = None,
    session: SessionDep = None,
):
    stmt = select(NotificationGateway).order_by(
        NotificationGateway.is_active.desc(), NotificationGateway.priority.asc()
    )
    if type:
        stmt = stmt.where(NotificationGateway.type == type)
    rows = (await session.execute(stmt)).scalars().all()
    return [_to_read(g) for g in rows]


@router.post("", response_model=NotificationGatewayRead, status_code=201)
async def create_gateway(
    payload: NotificationGatewayCreate, _: PrivilegedUser, session: SessionDep
):
    existing = (
        await session.execute(
            select(NotificationGateway).where(NotificationGateway.name == payload.name)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(409, "gateway name already exists")
    gateway = NotificationGateway(
        name=payload.name,
        type=payload.type,
        config_json=json.dumps(payload.config_json),
        is_active=payload.is_active,
        priority=payload.priority,
    )
    session.add(gateway)
    await session.commit()
    await session.refresh(gateway)
    return _to_read(gateway)


@router.get("/{gateway_id}", response_model=NotificationGatewayRead)
async def get_gateway(gateway_id: uuid.UUID, _: CurrentUser, session: SessionDep):
    gateway = (
        await session.execute(
            select(NotificationGateway).where(NotificationGateway.id == gateway_id)
        )
    ).scalar_one_or_none()
    if gateway is None:
        raise HTTPException(404, "gateway not found")
    return _to_read(gateway)


@router.patch("/{gateway_id}", response_model=NotificationGatewayRead)
async def update_gateway(
    gateway_id: uuid.UUID,
    payload: NotificationGatewayUpdate,
    _: PrivilegedUser,
    session: SessionDep,
):
    gateway = (
        await session.execute(
            select(NotificationGateway).where(NotificationGateway.id == gateway_id)
        )
    ).scalar_one_or_none()
    if gateway is None:
        raise HTTPException(404, "gateway not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "config_json" and value is not None:
            gateway.config_json = json.dumps(value)
        else:
            setattr(gateway, field, value)
    await session.commit()
    await session.refresh(gateway)
    return _to_read(gateway)


@router.delete("/{gateway_id}", status_code=204)
async def delete_gateway(gateway_id: uuid.UUID, _: PrivilegedUser, session: SessionDep):
    gateway = (
        await session.execute(
            select(NotificationGateway).where(NotificationGateway.id == gateway_id)
        )
    ).scalar_one_or_none()
    if gateway is None:
        raise HTTPException(404, "gateway not found")
    await session.delete(gateway)
    await session.commit()