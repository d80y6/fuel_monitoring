"""Notification domain models: gateway config + delivery log."""
from __future__ import annotations

import uuid as uuid_type
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from fmp.core.database import Base
from fmp.models.base import TimestampMixin


class NotificationGateway(TimestampMixin, Base):
    """Configured outbound channel (SMPP SMS or WhatsApp Business API)."""

    __tablename__ = "notification_gateways"

    id: Mapped[uuid_type.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_type.uuid4
    )
    name: Mapped[str] = mapped_column(String(64), unique=True)
    type: Mapped[str] = mapped_column(String(20))  # smpp | whatsapp
    config_json: Mapped[str] = mapped_column(Text)  # JSON-serialized channel config
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=10)


class NotificationLog(TimestampMixin, Base):
    __tablename__ = "notification_logs"

    id: Mapped[uuid_type.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_type.uuid4
    )
    allocation_id: Mapped[uuid_type.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("allocations.id")
    )
    gateway_id: Mapped[uuid_type.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notification_gateways.id")
    )
    channel: Mapped[str] = mapped_column(String(20))
    recipient_phone: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(32), default="PENDING")  # PENDING|SENT|FAILED|ACK
    provider_message_id: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))