"""Stations API: CRUD + nested dispensers (tenant-scoped)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from fmp.api.deps import CurrentUser, PrivilegedUser, SessionDep
from fmp.models import Dispenser, Site, Station
from fmp.schemas.org import (
    DispenserCreate,
    DispenserRead,
    DispenserUpdate,
    StationCreate,
    StationRead,
    StationUpdate,
)
from fmp.services import audit as audit_log

router = APIRouter(prefix="/api/v1/stations", tags=["stations"])


async def _get_scoped(session, station_id: uuid.UUID, caller) -> Station:
    station = (
        await session.execute(
            select(Station).where(Station.id == station_id)
        )
    ).scalar_one_or_none()
    if station is None or station.deleted_at is not None:
        raise HTTPException(404, "station not found")
    if caller.role != "admin":
        site = (
            await session.execute(select(Site.company_id).where(Site.id == station.site_id))
        ).scalar_one_or_none()
        if site != caller.company_id:
            raise HTTPException(404, "station not found")
    return station


def _site_scope_filter(caller):
    """Station.site_id selector constrained to the caller's company."""
    sites = select(Site.id).where(Site.deleted_at.is_(None))
    if caller.role != "admin":
        sites = sites.where(Site.company_id == caller.company_id)
    return sites.scalar_subquery()


@router.get("", response_model=list[StationRead])
async def list_stations(
    current: CurrentUser,
    session: SessionDep,
    site_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    stmt = (
        select(Station)
        .where(Station.deleted_at.is_(None), Station.site_id.in_(_site_scope_filter(current)))
    )
    if site_id:
        stmt = stmt.where(Station.site_id == site_id)
    rows = (
        await session.execute(stmt.order_by(Station.name).offset(offset).limit(limit))
    ).scalars().all()
    return rows


@router.post("", response_model=StationRead, status_code=201)
async def create_station(payload: StationCreate, current: PrivilegedUser, session: SessionDep):
    site = (
        await session.execute(
            select(Site).where(Site.id == payload.site_id, Site.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if site is None or (current.role != "admin" and site.company_id != current.company_id):
        raise HTTPException(404, "site not found")
    dup = (
        await session.execute(
            select(Station).where(Station.serial_number == payload.serial_number)
        )
    ).scalar_one_or_none()
    if dup is not None and dup.deleted_at is None:
        raise HTTPException(409, "station serial already exists")
    station = Station(**payload.model_dump())
    session.add(station)
    audit_log.record(
        session, actor=current, action="station.create", entity_type="station",
        company_id=site.company_id, detail={"name": station.name, "site_id": str(site.id)},
    )
    await session.commit()
    await session.refresh(station)
    return station


@router.get("/{station_id}", response_model=StationRead)
async def get_station(station_id: uuid.UUID, current: CurrentUser, session: SessionDep):
    return await _get_scoped(session, station_id, current)


@router.patch("/{station_id}", response_model=StationRead)
async def update_station(
    station_id: uuid.UUID, payload: StationUpdate, current: PrivilegedUser, session: SessionDep
):
    station = await _get_scoped(session, station_id, current)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(station, field, value)
    audit_log.record(
        session, actor=current, action="station.update", entity_type="station",
        entity_id=station.id, detail={"changed": sorted(changes)},
    )
    await session.commit()
    await session.refresh(station)
    return station


@router.delete("/{station_id}", status_code=204)
async def delete_station(station_id: uuid.UUID, current: PrivilegedUser, session: SessionDep):
    station = await _get_scoped(session, station_id, current)
    station.soft_delete()
    audit_log.record(
        session, actor=current, action="station.delete", entity_type="station",
        entity_id=station.id,
    )
    await session.commit()


@router.post("/{station_id}/restore", response_model=StationRead)
async def restore_station(station_id: uuid.UUID, current: PrivilegedUser, session: SessionDep):
    station = (
        await session.execute(select(Station).where(Station.id == station_id))
    ).scalar_one_or_none()
    if station is None:
        raise HTTPException(404, "station not found")
    if current.role != "admin":
        site = (
            await session.execute(select(Site.company_id).where(Site.id == station.site_id))
        ).scalar_one_or_none()
        if site != current.company_id:
            raise HTTPException(404, "station not found")
    station.restore()
    audit_log.record(
        session, actor=current, action="station.restore", entity_type="station",
        entity_id=station.id,
    )
    await session.commit()
    await session.refresh(station)
    return station


# --- dispensers ---------------------------------------------------------------
@router.post("/{station_id}/dispensers", response_model=DispenserRead, status_code=201)
async def create_dispenser(
    station_id: uuid.UUID, payload: DispenserCreate, current: PrivilegedUser, session: SessionDep
):
    station = await _get_scoped(session, station_id, current)
    dup = (
        await session.execute(
            select(Dispenser).where(Dispenser.serial_number == payload.serial_number)
        )
    ).scalar_one_or_none()
    if dup is not None:
        raise HTTPException(409, "dispenser serial already exists")
    dispenser = Dispenser(**{**payload.model_dump(), "station_id": station.id})
    session.add(dispenser)
    audit_log.record(
        session, actor=current, action="dispenser.create", entity_type="dispenser",
        detail={"name": dispenser.name, "station_id": str(station.id)},
    )
    await session.commit()
    await session.refresh(dispenser)
    return dispenser


@router.get("/{station_id}/dispensers", response_model=list[DispenserRead])
async def station_dispensers(station_id: uuid.UUID, current: CurrentUser, session: SessionDep):
    await _get_scoped(session, station_id, current)
    rows = (
        await session.execute(
            select(Dispenser).where(Dispenser.station_id == station_id).order_by(Dispenser.name)
        )
    ).scalars().all()
    return rows


@router.patch("/{station_id}/dispensers/{dispenser_id}", response_model=DispenserRead)
async def update_dispenser(
    station_id: uuid.UUID,
    dispenser_id: uuid.UUID,
    payload: DispenserUpdate,
    current: PrivilegedUser,
    session: SessionDep,
):
    await _get_scoped(session, station_id, current)
    dispenser = (
        await session.execute(
            select(Dispenser).where(
                Dispenser.id == dispenser_id, Dispenser.station_id == station_id
            )
        )
    ).scalar_one_or_none()
    if dispenser is None:
        raise HTTPException(404, "dispenser not found in this station")
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(dispenser, field, value)
    audit_log.record(
        session, actor=current, action="dispenser.update", entity_type="dispenser",
        entity_id=dispenser.id, detail={"changed": sorted(changes)},
    )
    await session.commit()
    await session.refresh(dispenser)
    return dispenser


@router.delete("/{station_id}/dispensers/{dispenser_id}", status_code=204)
async def delete_dispenser(
    station_id: uuid.UUID,
    dispenser_id: uuid.UUID,
    current: PrivilegedUser,
    session: SessionDep,
):
    """Soft deactivate: dispense history must stay, so dispensers disable instead
    of being removed."""
    await _get_scoped(session, station_id, current)
    dispenser = (
        await session.execute(
            select(Dispenser).where(
                Dispenser.id == dispenser_id, Dispenser.station_id == station_id
            )
        )
    ).scalar_one_or_none()
    if dispenser is None:
        raise HTTPException(404, "dispenser not found in this station")
    dispenser.is_active = False
    audit_log.record(
        session, actor=current, action="dispenser.deactivate", entity_type="dispenser",
        entity_id=dispenser.id,
    )
    await session.commit()
