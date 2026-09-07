"""Pydantic v2 schemas for notification dispatch."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from fmp.schemas.dispensing import ExcelIngestResult


class ExcelIngestOutcome(BaseModel):
    """Result of an Excel upload: batch summary + codes awaiting dispatch."""
    result: ExcelIngestResult
    pending_dispatch: list["PendingDispatch"]


class PendingDispatch(BaseModel):
    """A code that must be delivered to an employee right away."""
    allocation_id: uuid.UUID
    employee_id: str
    employee_name: str
    phone: str
    code: str
    liters: float
    invoice_number: str | None = None
    channel: Literal["sms", "whatsapp"] | None = None


class DispatchResult(BaseModel):
    allocation_id: uuid.UUID
    phone: str
    channel: Literal["sms", "whatsapp"]
    status: Literal["SENT", "FAILED"]
    gateway_id: uuid.UUID | None = None
    provider_message_id: str | None = None
    error: str | None = None


class NotificationLogOut(BaseModel):
    id: uuid.UUID
    allocation_id: uuid.UUID | None = None
    channel: str
    recipient_phone: str
    status: str
    provider_message_id: str | None = None
    error_message: str | None = None
    retry_count: int
    sent_at: datetime | None = None


class GatewayConfigOut(BaseModel):
    id: uuid.UUID
    name: str
    type: Literal["smpp", "whatsapp"]
    is_active: bool
    priority: int


class GatewayUpsert(BaseModel):
    name: str = Field(min_length=2, max_length=64)
    type: Literal["smpp", "whatsapp"]
    config: dict
    is_active: bool = True
    priority: int = 10