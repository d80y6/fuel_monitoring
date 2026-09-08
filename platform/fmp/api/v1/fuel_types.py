"""Fuel type API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from fmp.api.deps import CurrentUser, PrivilegedUser, SessionDep
from fmp.models import FuelType
from fmp.schemas.fuel import FuelTypeCreate, FuelTypeRead

router = APIRouter(prefix="/api/v1/fuel-types", tags=["fuel-types"])


@router.get("", response_model=list[FuelTypeRead])
async def list_fuel_types(_: CurrentUser, session: SessionDep):
    rows = (await session.execute(
        select(FuelType).order_by(FuelType.code)
    )).scalars().all()
    return rows


@router.post("", response_model=FuelTypeRead, status_code=201)
async def create_fuel_type(payload: FuelTypeCreate, _: PrivilegedUser, session: SessionDep):
    dup = (await session.execute(
        select(FuelType).where(FuelType.code == payload.code)
    )).scalar_one_or_none()
    if dup is not None:
        raise HTTPException(409, "fuel type code already exists")
    fuel = FuelType(**payload.model_dump())
    session.add(fuel)
    await session.commit()
    await session.refresh(fuel)
    return fuel
