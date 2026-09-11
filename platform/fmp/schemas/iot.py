"""Pydantic v2 schemas for IoT gateway command API."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CommandType = Literal[
    "reboot", "status_probe", "pause_reporting", "resume_reporting",
    "set_interval", "recalibrate", "zero_tank", "push_config",
]


class IoTGatewayCreate(BaseModel):
    gateway_mac: str = Field(min_length=1, max_length=17)
    name: str | None = Field(default=None, max_length=100)
    firmware_version: str | None = Field(default=None, max_length=32)


class IoTGatewayUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    firmware_version: str | None = Field(default=None, max_length=32)
    is_active: bool | None = None
    tank_ids: list[uuid.UUID] | None = None


class IoTGatewayRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    gateway_mac: str
    name: str
    firmware_version: str | None
    last_seen: datetime | None
    connection_status: str
    is_active: bool
    tank_ids: list[uuid.UUID] = Field(default_factory=list)
    created_at: datetime


class IoTCommandCreate(BaseModel):
    command_type: CommandType
    payload: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_payload(self):
        p = self.payload
        empty_ok = {"reboot", "status_probe", "resume_reporting"}
        if self.command_type in empty_ok:
            if p:
                raise ValueError(f"{self.command_type} accepts no payload")
            return self
        if self.command_type == "pause_reporting":
            if "duration_s" in p and (not isinstance(p["duration_s"], int) or p["duration_s"] < 1):
                raise ValueError("duration_s must be a positive integer")
            return self
        if self.command_type == "set_interval":
            if not isinstance(p.get("interval_s"), int) or p.get("interval_s", 0) < 1:
                raise ValueError("interval_s must be a positive integer (seconds)")
            return self
        if self.command_type == "recalibrate":
            if not p.get("sensor") or not isinstance(p["sensor"], str):
                raise ValueError("recalibrate requires sensor (str)")
            ref = p.get("reference_pressure_bar")
            if not isinstance(ref, float) and not isinstance(ref, int):
                raise ValueError("recalibrate requires reference_pressure_bar (float)")
            return self
        if self.command_type == "zero_tank":
            if not p.get("tank_serial") or not isinstance(p["tank_serial"], str):
                raise ValueError("zero_tank requires tank_serial (str)")
            if "level_m" in p and not isinstance(p["level_m"], (int, float)):
                raise ValueError("level_m must be numeric")
            return self
        if self.command_type == "push_config":
            if not p:
                raise ValueError("push_config requires a non-empty config object")
            return self
        raise ValueError(f"unsupported command_type {self.command_type}")


class IoTCommandRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    command_id: uuid.UUID
    gateway_id: uuid.UUID
    command_type: str
    payload_json: dict
    status: str
    attempts: int
    max_attempts: int
    sent_at: datetime | None
    next_retry_at: datetime | None
    ack_status: str | None
    ack_detail: str | None
    ack_received_at: datetime | None
    error_message: str | None
    created_at: datetime


class IoTCommandIssue(BaseModel):
    command_id: uuid.UUID
    status: str