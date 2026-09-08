"""Strapping-table DTOs."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrappingPoint(BaseModel):
    height: float = Field(ge=0)
    volume: float = Field(ge=0)


class StrappingTableUpsert(BaseModel):
    calibration_data: list[StrappingPoint] = Field(min_length=2)
    interpolation_method: Literal["linear", "cubic_spline"] = "linear"

    @model_validator(mode="after")
    def _ascending_heights(self):
        heights = [p.height for p in self.calibration_data]
        if heights != sorted(heights):
            raise ValueError("calibration_data heights must be ascending")
        return self


class StrappingTableRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tank_id: uuid.UUID
    calibration_data: list[StrappingPoint]
    interpolation_method: Literal["linear", "cubic_spline"]
    created_at: datetime
