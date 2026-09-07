"""Tank / telemetry API schemas (Pydantic v2)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

TANK_ORIENTATIONS = ("vertical", "horizontal")


class TankBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    site_id: uuid.UUID
    sensor_serial_number: str = Field(min_length=1, max_length=64)
    device_address: int = 1
    tank_orientation: str = Field(default="vertical", pattern="^(vertical|horizontal)$")
    tank_diameter: float = Field(gt=0)
    tank_height: float | None = Field(default=None, gt=0)
    tank_length: float | None = Field(default=None, gt=0)
    tank_volume: float = Field(gt=0)
    fluid_density: float = Field(gt=0)
    elevation: float | None = None
    calibration_factor: float = 1.0
    atmospheric_pressure: float = 0.0
    low_level_threshold: float | None = None
    critical_level_threshold: float | None = None
    high_level_threshold: float | None = None
    low_volume_threshold: float | None = None
    high_volume_threshold: float | None = None
    is_active: bool = True
    gateway_mac: str | None = Field(default=None, max_length=17)


class TankCreate(TankBase):
    pass


class TankRead(TankBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    connection_status: str
    last_connection: datetime | None


class TelemetryPoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    timestamp: datetime
    pressure: float | None = None
    temperature: float | None = None
    level: float | None = None
    volume: float | None = None
    flow_rate: float | None = None
    fill_percent: float | None = None
    is_outlier: bool = False


class AlarmSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tank_id: uuid.UUID
    timestamp: datetime
    type: str
    level: str
    message: str
    value: float | None = None
    acknowledged: bool
    acknowledged_at: datetime | None = None


class AlarmAckOutcome(BaseModel):
    alarm_id: uuid.UUID
    acknowledged: bool