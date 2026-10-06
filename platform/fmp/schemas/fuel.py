"""Fuel type DTOs."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FuelTypeBase(BaseModel):
    code: str = Field(min_length=1, max_length=32, pattern="^[a-z0-9_]+$")
    name: str = Field(min_length=1, max_length=64)
    base_density: float = Field(gt=0)
    thermal_expansion_coeff: float = Field(gt=0)
    max_vapor_pressure: float = Field(ge=0)
    viscosity_cst: float = Field(ge=0)


class FuelTypeCreate(FuelTypeBase):
    pass


class FuelTypeRead(FuelTypeBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime


class FuelTypeUpdate(BaseModel):
    """Partial update.

    ``code`` is deliberately immutable: it is the stable key used by Excel quota
    sheets and by device configuration, so renaming it would silently orphan
    historical rows that reference it by code. Create a new code instead.
    """

    name: str | None = Field(default=None, min_length=1, max_length=64)
    base_density: float | None = Field(default=None, gt=0)
    thermal_expansion_coeff: float | None = Field(default=None, gt=0)
    max_vapor_pressure: float | None = Field(default=None, ge=0)
    viscosity_cst: float | None = Field(default=None, ge=0)
