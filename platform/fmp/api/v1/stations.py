"""Stations API: CRUD + nested dispensers."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from fmp.api.deps import CurrentUser, PrivilegedUser, SessionDep
from fmp.models import Dispenser, Station
from fmp.schemas.org import (
    DispenserCreate,
    DispenserRead,
    StationCreate,
    StationRead,
    StationUpdate,
)

router = APIRouter(prefix="/api/v1/stations", tags=["stations"])


@router.get("", response_model=list[StationRead])
async def list_stations(
    site_id: uuid.UUID | None = None,
    current: CurrentUser = None,
    session: SessionDep = None,
):
    del current
    stmt = select(Station).where(Station.deleted_at.is_(None))
    if site_id:
        stmt = stmt.where(Station.site_id == site_id)
    rows = (await session.execute(stmt.order_by(Station.name))).scalars().all()
    return rows


@router.post("", response_model=StationRead, status_code=201)
async def create_station(payload: StationCreate, _: PrivilegedUser, session: SessionDep):
    dup = (
        await session.execute(select(Station).where(Station.serial_number == payload.serial_number))
    ).scalar_one_or_none()
    if dup is not None and dup.deleted_at is None:
        raise HTTPException(409, "station serial already exists")
    station = Station(**payload.model_dump())
    session.add(station)
    await session.commit()
    await session.refresh(station)
    return station


@router.get("/{station_id}", response_model=StationRead)
async def get_station(station_id: uuid.UUID, _: CurrentUser, session: SessionDep):
    station = (
        await session.execute(select(Station).where(Station.id == station_id))
    ).scalar_one_or_none()
    if station is None or station.deleted_at is not None:
        raise HTTPException(404, "station not found")
    return station


@router.patch("/{station_id}", response_model=StationRead)
async def update_station(
    station_id: uuid.UUID, payload: StationUpdate, _: PrivilegedUser, session: SessionDep
):
    station = (
        await session.execute(select(Station).where(Station.id == station_id))
    ).scalar_one_or_none()
    if station is None or station.deleted_at is not None:
        raise HTTPException(404, "station not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(station, field, value)
    await session.commit()
    await session.refresh(station)
    return station


@router.delete("/{station_id}", status_code=204)
async def delete_station(station_id: uuid.UUID, _: PrivilegedUser, session: SessionDep):
    station = (
        await session.execute(select(Station).where(Station.id == station_id))
    ).scalar_one_or_none()
    if station is None or station.deleted_at is not None:
        raise HTTPException(404, "station not found")
    station.soft_delete()
    await session.commit()


@router.post("/{station_id}/dispensers", response_model=DispenserRead, status_code=201)
async def create_dispenser(
    station_id: uuid.UUID, payload: DispenserCreate, _: PrivilegedUser, session: SessionDep
):
    dispenser = Dispenser(**{**payload.model_dump(), "station_id": station_id})
    session.add(dispenser)
    await session.commit()
    await session.refresh(dispenser)
    return dispenser


@router.get("/{station_id}/dispensers", response_model=list[DispenserRead])
async def station_dispensers(station_id: uuid.UUID, _: CurrentUser, session: SessionDep):
    rows = (
        await session.execute(
            select(Dispenser).where(Dispenser.station_id == station_id).order_by(Dispenser.name)
        )
    ).scalars().all()
    return rows