"""Fuel type API — the platform-wide product catalogue.

Fuel types are reference data shared by every tenant (gasoline, diesel, …), not
per-organization rows, so the list is global by design. Writes are restricted to
management roles and audited.

Deleting a fuel type is refused while any tank still references it: those tanks
carry measured volumes computed with that product's density and expansion
coefficient, so removing it would leave uninterpretable history behind.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from fmp.api.deps import AdminUser, CurrentUser, PrivilegedUser, SessionDep
from fmp.models import FuelType, Tank
from fmp.schemas.fuel import FuelTypeCreate, FuelTypeRead, FuelTypeUpdate
from fmp.services import audit as audit_log

router = APIRouter(prefix="/api/v1/fuel-types", tags=["fuel-types"])


@router.get("", response_model=list[FuelTypeRead])
async def list_fuel_types(_: CurrentUser, session: SessionDep):
    rows = (
        await session.execute(select(FuelType).order_by(FuelType.code))
    ).scalars().all()
    return rows


@router.post("", response_model=FuelTypeRead, status_code=201)
async def create_fuel_type(payload: FuelTypeCreate, current: PrivilegedUser, session: SessionDep):
    dup = (
        await session.execute(select(FuelType).where(FuelType.code == payload.code))
    ).scalar_one_or_none()
    if dup is not None:
        raise HTTPException(409, "fuel type code already exists")
    fuel = FuelType(**payload.model_dump())
    session.add(fuel)
    await session.flush()
    audit_log.record(
        session, actor=current, action="fuel_type.create", entity_type="fuel_type",
        entity_id=fuel.id, detail={"code": fuel.code},
    )
    await session.commit()
    await session.refresh(fuel)
    return fuel


async def _get_fuel_type(session, code: str) -> FuelType:
    fuel = (
        await session.execute(select(FuelType).where(FuelType.code == code))
    ).scalar_one_or_none()
    if fuel is None:
        raise HTTPException(404, "fuel type not found")
    return fuel


@router.patch("/{code}", response_model=FuelTypeRead)
async def update_fuel_type(
    code: str, payload: FuelTypeUpdate, current: AdminUser, session: SessionDep
):
    """Update product properties.

    Density and expansion changes affect how *future* volumes are computed;
    historical measurements keep the coefficients that were in force when they
    were recorded (each row stores the density actually used).
    """
    fuel = await _get_fuel_type(session, code)
    changed = payload.model_dump(exclude_unset=True)
    for field, value in changed.items():
        setattr(fuel, field, value)
    audit_log.record(
        session, actor=current, action="fuel_type.update", entity_type="fuel_type",
        entity_id=fuel.id, detail={"code": fuel.code, "changed": sorted(changed)},
    )
    await session.commit()
    await session.refresh(fuel)
    return fuel


@router.delete("/{code}", status_code=204)
async def delete_fuel_type(code: str, current: AdminUser, session: SessionDep):
    """Delete a fuel type, refusing while tanks still reference it."""
    fuel = await _get_fuel_type(session, code)
    in_use = (
        await session.execute(
            select(func.count()).select_from(Tank).where(Tank.fuel_type_id == fuel.id)
        )
    ).scalar_one()
    if in_use:
        raise HTTPException(
            409,
            f"fuel type is used by {in_use} tank(s); reassign them before deleting",
        )
    audit_log.record(
        session, actor=current, action="fuel_type.delete", entity_type="fuel_type",
        entity_id=fuel.id, detail={"code": fuel.code},
    )
    await session.delete(fuel)
    await session.commit()
