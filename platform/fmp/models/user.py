"""UploadBatch record + User model."""
from __future__ import annotations

import uuid as uuid_type
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from fmp.core.database import Base
from fmp.models.base import SoftDeleteMixin, TimestampMixin


class UploadBatch(TimestampMixin, Base):
    __tablename__ = "upload_batches"

    id: Mapped[uuid_type.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_type.uuid4
    )
    filename: Mapped[str] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255))
    uploaded_by_id: Mapped[uuid_type.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    successful_rows: Mapped[int] = mapped_column(Integer, default=0)
    failed_rows: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="PROCESSING")
    error_log: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class User(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid_type.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_type.uuid4
    )
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    first_name: Mapped[str | None] = mapped_column(String(64))
    last_name: Mapped[str | None] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(20), default="user")  # admin|company_admin|user
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    phone: Mapped[str | None] = mapped_column(String(20))
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))