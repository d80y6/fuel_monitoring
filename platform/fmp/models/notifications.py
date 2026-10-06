"""Notification domain models: gateway config + delivery log."""
from __future__ import annotations

import uuid as uuid_type
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from fmp.core.database import Base
from fmp.models.base import TimestampMixin


class NotificationGateway(TimestampMixin, Base):
    """Configured outbound channel (SMPP SMS, WhatsApp, SMTP email or webhook).

    ``company_id`` scopes the channel to one tenant; ``None`` is a
    platform-wide channel usable by every tenant. Credentials inside
    ``config_json`` are write-only over the API — see
    :mod:`fmp.services.notifications.secrets`.
    """

    __tablename__ = "notification_gateways"
    #: Channel names are unique per tenant. Postgres treats NULL company_id as
    #: distinct, so platform-wide channel names are additionally guarded in the
    #: API layer.
    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_notification_gateways_company_name"),
    )

    id: Mapped[uuid_type.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_type.uuid4
    )
    #: Tenant binding. ``None`` = platform-wide channel shared by all tenants.
    company_id: Mapped[uuid_type.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(64), index=True)
    type: Mapped[str] = mapped_column(String(20))  # smpp | whatsapp | email | webhook
    config_json: Mapped[str] = mapped_column(Text)  # JSON-serialized channel config
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=10)


class NotificationRule(TimestampMixin, Base):
    """Routing rule: when an event fires, notify recipients over a channel.

    ``event_type`` currently supports ``alarm``. Recipients are explicit
    targets (MSISDN / email / webhook URL) resolved through an active
    :class:`NotificationGateway` of the matching ``channel`` type.
    ``company_id`` scopes the rule to one tenant; ``None`` = platform-wide.
    """

    __tablename__ = "notification_rules"

    id: Mapped[uuid_type.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_type.uuid4
    )
    company_id: Mapped[uuid_type.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    event_type: Mapped[str] = mapped_column(String(40), default="alarm", index=True)
    min_level: Mapped[str] = mapped_column(String(20), default="WARNING")  # WARNING|CRITICAL
    site_id: Mapped[uuid_type.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id"), index=True
    )
    channel: Mapped[str] = mapped_column(String(20))  # sms|whatsapp|email|webhook
    targets: Mapped[list] = mapped_column(JSONB, default=list)  # ["+2507..", "ops@x.io", "https://hook/.."]
    template: Mapped[str | None] = mapped_column(Text)  # optional {placeholders}
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class NotificationLog(TimestampMixin, Base):
    __tablename__ = "notification_logs"

    id: Mapped[uuid_type.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_type.uuid4
    )
    #: Tenant the delivery belongs to (inherited from the triggering record).
    company_id: Mapped[uuid_type.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), index=True
    )
    allocation_id: Mapped[uuid_type.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("allocations.id")
    )
    #: Free-form origin tag: "dispense_code" (default legacy), "alarm", ...
    event_type: Mapped[str] = mapped_column(String(32), default="dispense_code", index=True)
    #: Polymorphic reference to the triggering record (alarm id, ...).
    event_ref: Mapped[str | None] = mapped_column(String(64), index=True)
    gateway_id: Mapped[uuid_type.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notification_gateways.id")
    )
    channel: Mapped[str] = mapped_column(String(20))
    recipient: Mapped[str] = mapped_column(String(254))
    status: Mapped[str] = mapped_column(String(32), default="PENDING")  # PENDING|SENT|FAILED|ACK
    provider_message_id: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))