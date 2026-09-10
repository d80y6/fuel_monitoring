"""ORMs: IoTGateway and GatewayCommand (edge device command plane)."""
from __future__ import annotations

import uuid as uuid_type
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fmp.core.database import Base
from fmp.models.base import TimestampMixin, UUIDPrimaryKeyMixin

COMMAND_TYPES = (
    "reboot", "status_probe", "pause_reporting", "resume_reporting",
    "set_interval", "recalibrate", "zero_tank", "push_config",
)


class IoTGateway(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An edge gateway registered against the platform."""

    __tablename__ = "iot_gateways"

    gateway_mac: Mapped[str] = mapped_column(String(17), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100), default="", index=True)
    firmware_version: Mapped[str | None] = mapped_column(String(32))
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    connection_status: Mapped[str] = mapped_column(String(20), default="offline")
    is_active: Mapped[bool] = mapped_column(default=False)

    commands: Mapped[list["GatewayCommand"]] = relationship(back_populates="gateway")
    tanks: Mapped[list["Tank"]] = relationship(  # noqa: F821
        back_populates="gateway"
    )


class GatewayCommand(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A command issued to an IoT gateway, tracked to ack/failure."""

    __tablename__ = "gateway_commands"

    gateway_id: Mapped[uuid_type.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iot_gateways.id"), index=True
    )
    command_id: Mapped[uuid_type.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, default=uuid_type.uuid4
    )
    command_type: Mapped[str] = mapped_column(String(32), index=True)
    payload_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ack_status: Mapped[str | None] = mapped_column(String(32))
    ack_detail: Mapped[str | None] = mapped_column(String(255))
    ack_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(String(255))

    gateway: Mapped["IoTGateway"] = relationship(back_populates="commands")