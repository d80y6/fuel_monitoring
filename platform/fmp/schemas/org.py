"""Organizational schemas: Company / Site / Station / Dispenser (Pydantic v2)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# --- Company ----------------------------------------------------------------
class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    address: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None


class CompanyUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    address: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    created_at: datetime


# --- Site -------------------------------------------------------------------
class SiteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    company_id: uuid.UUID
    address: str | None = None
    location: str | None = None
    is_active: bool = True


class SiteUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    location: str | None = None
    is_active: bool | None = None


class SiteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    company_id: uuid.UUID
    address: str | None = None
    location: str | None = None
    is_active: bool
    created_at: datetime


# --- Station ----------------------------------------------------------------
class StationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    site_id: uuid.UUID
    serial_number: str = Field(min_length=1, max_length=64)
    raspberry_pi_id: str | None = None
    firmware_version: str | None = None


class StationUpdate(BaseModel):
    name: str | None = None
    raspberry_pi_id: str | None = None
    firmware_version: str | None = None
    connection_status: str | None = None


class StationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    site_id: uuid.UUID
    serial_number: str
    raspberry_pi_id: str | None = None
    firmware_version: str | None = None
    connection_status: str
    last_heartbeat: datetime | None = None


# --- Dispenser ----------------------------------------------------------------
class DispenserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    station_id: uuid.UUID | None = None  # optional: POST /stations/{id}/dispensers injects it
    serial_number: str = Field(min_length=1, max_length=64)
    modbus_address: int = 1
    dispenser_model: str | None = None


class DispenserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    station_id: uuid.UUID
    serial_number: str
    modbus_address: int
    dispenser_model: str | None = None
    is_active: bool