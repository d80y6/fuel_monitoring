"""Audit domain: immutable record of security- and business-relevant actions."""
from __future__ import annotations

import uuid as uuid_type
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from fmp.core.database import Base


class AuditEvent(Base):
    """Append-only audit trail entry.

    Written by the ``fmp.services.audit`` helper on security-relevant
    mutations (auth, user admin, threshold/rule changes, gateway commands,
    report exports...). ``company_id`` is denormalized from the actor so
    tenant admins can read only their own company's trail.
    """

    __tablename__ = "audit_events"

    id: Mapped[uuid_type.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_type.uuid4
    )
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    actor_id: Mapped[uuid_type.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    actor_username: Mapped[str | None] = mapped_column(String(64))
    company_id: Mapped[uuid_type.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), index=True
    )
    action: Mapped[str] = mapped_column(String(64), index=True)  # e.g. "user.create"
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(64), index=True)
    detail: Mapped[dict | None] = mapped_column(JSONB)
