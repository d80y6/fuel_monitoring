"""Wire schemas for telemetry frames arriving over HTTP fallback (G-114).

The MQTT path is schema-checked at the broker by topic convention; the HTTP
fallback (``POST /api/v1/ingest/readings``) previously accepted a bare ``dict``,
so a malformed or hostile body reached the calibration math. These schemas make
the fallback path as strict as the broker path: unknown structure → 422, and a
frame with no usable measurement is rejected before it can corrupt tank state.

Validation rules chosen for industrial probes:

* ``pressure`` is required and must be a finite number (a level cannot be
  derived without it).
* ``temperature`` is optional (some probes are pressure-only) but must be in a
  physically plausible range for a storage tank: -60 °C … 150 °C.
* ``status`` is an integer device status code; non-integers are rejected.
* ``timestamp`` must be ISO-8601 and is normalized to UTC. Absurd timestamps
  (before 2000 or more than a day in the future) are rejected as device faults
  rather than silently skewing history.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: A storage-tank probe cannot plausibly report outside these bounds.
MIN_TEMPERATURE_C = -60.0
MAX_TEMPERATURE_C = 150.0
#: Absolute floor for bar readings; negative absolute pressure is meaningless.
MIN_PRESSURE_BAR = -2.0
#: Sanity ceiling — beyond this a frame is a device fault, not a real tank.
MAX_PRESSURE_BAR = 50.0
#: Device clocks drift, but a frame from before this epoch is a fault.
EARLIEST_PLAUSIBLE = datetime(2000, 1, 1, tzinfo=timezone.utc)
#: Frames may be buffered offline, so allow modest future skew.
MAX_FUTURE_SKEW = timedelta(days=1)


class TelemetryFrame(BaseModel):
    """One tank pressure/temperature measurement."""

    model_config = ConfigDict(extra="allow")

    sensor_serial: str | None = Field(default=None, max_length=64)
    sensor_serial_number: str | None = Field(default=None, max_length=64)
    tank_id: str | None = Field(default=None, max_length=64)
    pressure: float
    temperature: float | None = None
    status: int = 0
    timestamp: datetime | None = None

    @field_validator("pressure")
    @classmethod
    def _pressure_in_range(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("pressure must be a finite number")
        if not (MIN_PRESSURE_BAR <= v <= MAX_PRESSURE_BAR):
            raise ValueError(
                f"pressure {v} out of plausible range "
                f"[{MIN_PRESSURE_BAR}, {MAX_PRESSURE_BAR}] bar"
            )
        return v

    @field_validator("temperature")
    @classmethod
    def _temperature_in_range(cls, v: float | None) -> float | None:
        if v is None:
            return None
        if not math.isfinite(v):
            raise ValueError("temperature must be a finite number")
        if not (MIN_TEMPERATURE_C <= v <= MAX_TEMPERATURE_C):
            raise ValueError(
                f"temperature {v} out of plausible range "
                f"[{MIN_TEMPERATURE_C}, {MAX_TEMPERATURE_C}] degC"
            )
        return v

    @field_validator("timestamp")
    @classmethod
    def _timestamp_plausible(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return None
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        else:
            v = v.astimezone(timezone.utc)
        if v < EARLIEST_PLAUSIBLE:
            raise ValueError("device timestamp predates 2000 — suspect device clock")
        if v > datetime.now(timezone.utc) + MAX_FUTURE_SKEW:
            raise ValueError("device timestamp is more than a day in the future")
        return v

    def as_frame(self) -> dict[str, Any]:
        """Normalized dict for the pipeline (UTC-aware timestamp)."""
        return {
            "sensor_serial": self.sensor_serial or self.sensor_serial_number,
            "tank_id": self.tank_id,
            "pressure": self.pressure,
            "temperature": self.temperature,
            "status": self.status,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


class BackfillBatch(BaseModel):
    """A replay of offline-buffered frames."""

    model_config = ConfigDict(extra="ignore")

    frames: list[TelemetryFrame] = Field(min_length=1, max_length=5000)


class IngestOutcome(BaseModel):
    accepted: int
    rejected: int
    errors: list[str] = Field(default_factory=list)
