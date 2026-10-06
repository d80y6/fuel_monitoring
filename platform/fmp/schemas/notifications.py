"""Pydantic v2 schemas for notification gateways, rules, dispatch and logs."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from fmp.schemas.dispensing import ExcelIngestResult

#: Channels with a real, implemented sender in
#: ``fmp.services.notifications.dispatcher``. ``sms`` maps to SMPP gateways
#: (the operator-facing name used by the seed/UI); the legacy ``whatsapp``
#: name is kept for the Meta Cloud API channel. ``email`` is SMTP.
#: ``webhook`` posts a JSON document to a configured URL.
GATEWAY_TYPES = ("sms", "smpp", "whatsapp", "email", "webhook")


def _channel_literals() -> tuple[str, ...]:
    return GATEWAY_TYPES


class NotificationGatewayCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    type: Literal["sms", "smpp", "whatsapp", "email", "webhook"]
    config_json: dict = Field(default_factory=dict)
    is_active: bool = True
    priority: int = 10


class NotificationGatewayUpdate(BaseModel):
    is_active: bool | None = None
    priority: int | None = None
    config_json: dict | None = None


class NotificationGatewayRead(BaseModel):
    """Public-shaped gateway row: ``config_json`` is secret-masked.

    Secret values (passwords, tokens, credentials) are never returned over the
    API; the mask preserves key names so the UI can show which fields are
    configured. Writing a masked value back preserves the stored secret.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    type: str
    config_json: dict
    is_active: bool
    priority: int
    company_id: uuid.UUID | None = None
    created_at: datetime


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
    channel: Literal["sms", "smpp", "whatsapp"] | None = None
    #: Tenant owning the allocation — selects the tenant's notification channel.
    company_id: uuid.UUID | None = None


class DispatchResult(BaseModel):
    allocation_id: uuid.UUID
    phone: str
    channel: Literal["sms", "smpp", "whatsapp"]
    status: Literal["SENT", "FAILED"]
    gateway_id: uuid.UUID | None = None
    provider_message_id: str | None = None
    error: str | None = None


class NotificationLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID | None = None
    allocation_id: uuid.UUID | None = None
    event_type: str = "dispense_code"
    event_ref: str | None = None
    channel: str
    recipient: str
    status: str
    provider_message_id: str | None = None
    error_message: str | None = None
    retry_count: int
    sent_at: datetime | None = None


# ---------------------------------------------------------------------------
# Notification rules (event-driven notifications, e.g. alarms)
# ---------------------------------------------------------------------------
class NotificationRuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    event_type: str = Field(default="alarm", pattern="^alarm$")
    min_level: Literal["WARNING", "CRITICAL"] = "WARNING"
    site_id: uuid.UUID | None = None
    channel: Literal["sms", "smpp", "whatsapp", "email", "webhook"]
    targets: list[str] = Field(min_length=1, max_length=50)
    template: str | None = Field(default=None, max_length=2000)
    company_id: uuid.UUID | None = None
    enabled: bool = True


class NotificationRuleUpdate(BaseModel):
    name: str | None = None
    min_level: Literal["WARNING", "CRITICAL"] | None = None
    site_id: uuid.UUID | None = None
    channel: Literal["sms", "smpp", "whatsapp", "email", "webhook"] | None = None
    targets: list[str] | None = Field(default=None, min_length=1, max_length=50)
    template: str | None = Field(default=None, max_length=2000)
    enabled: bool | None = None


class NotificationRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID | None
    name: str
    event_type: str
    min_level: str
    site_id: uuid.UUID | None
    channel: str
    targets: list[str]
    template: str | None
    enabled: bool
    created_at: datetime


class EventDispatchSummary(BaseModel):
    event_type: str
    evaluated_rules: int
    sent: int
    failed: int
