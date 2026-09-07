"""Totalizer (secret counter meter) API schemas."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TotalizerPoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    timestamp: datetime
    station_id: uuid.UUID
    dispenser_id: uuid.UUID
    totalizer_value: int
    cumulative_liters: float | None = None
    source: str | None = None