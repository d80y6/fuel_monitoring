"""Tank / telemetry API schemas (Pydantic v2)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

TANK_ORIENTATIONS = ("vertical", "horizontal")

TANK_SHAPES = ("vertical_cylinder", "horizontal_cylinder", "rectangular", "spherical", "horizontal_elliptical_ends", "custom_strapping")

_ORIENT_PATTERN = "^(?:" + "|".join(TANK_ORIENTATIONS) + ")$"
_SHAPE_PATTERN = "^(?:" + "|".join(TANK_SHAPES) + ")$"


class TankBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    site_id: uuid.UUID
    sensor_serial_number: str = Field(min_length=1, max_length=64)
    device_address: int = 1
    tank_orientation: str = Field(default="vertical", pattern=_ORIENT_PATTERN)
    tank_shape: str = Field(default="vertical_cylinder", pattern=_SHAPE_PATTERN)
    tank_diameter: float = Field(gt=0)
    tank_height: float | None = Field(default=None, gt=0)
    tank_length: float | None = Field(default=None, gt=0)
    dish_depth: float | None = Field(default=None, gt=0)
    tank_width: float | None = Field(default=None, gt=0)
    fuel_type_id: uuid.UUID
    strapping_table_id: uuid.UUID | None = None
    tank_volume: float = Field(gt=0)
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
    @model_validator(mode="after")
    def _shape_consistency(self):
        if self.tank_shape == "vertical_cylinder" and self.tank_orientation != "vertical":
            raise ValueError("vertical_cylinder requires vertical tank_orientation")
        if self.tank_shape in ("horizontal_cylinder", "spherical", "horizontal_elliptical_ends") and self.tank_orientation != "horizontal":
            raise ValueError(f"{self.tank_shape} requires horizontal tank_orientation")
        if self.tank_shape == "rectangular" and not (self.tank_width and self.tank_length and self.tank_height):
            raise ValueError("rectangular requires tank_width, tank_length and tank_height")
        if self.tank_shape == "horizontal_elliptical_ends" and self.dish_depth is None:
            raise ValueError("horizontal_elliptical_ends requires dish_depth")
        if self.tank_shape == "custom_strapping" and self.strapping_table_id is None:
            raise ValueError("custom_strapping requires strapping_table_id")
        return self


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
    gov_volume: float | None = None
    net_volume: float | None = None
    density_at_temperature: float | None = None
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