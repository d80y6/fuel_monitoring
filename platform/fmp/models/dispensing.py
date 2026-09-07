"""Dispensing domain models: Allocation, DispenseCode, Transaction, Totalizer."""
from __future__ import annotations

import uuid as uuid_type
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
)
from sqlalchemy import Identity
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fmp.core.database import Base
from fmp.models.base import TimestampMixin


def _uuid_col(fk: str) -> Mapped[uuid_type.UUID]:
    return mapped_column(UUID(as_uuid=True), ForeignKey(fk), nullable=False)


class Allocation(TimestampMixin, Base):
    __tablename__ = "allocations"

    id: Mapped[uuid_type.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_type.uuid4
    )
    employee_id: Mapped[uuid_type.UUID] = _uuid_col("employees.id")
    upload_batch_id: Mapped[uuid_type.UUID] = _uuid_col("upload_batches.id")
    company_id: Mapped[uuid_type.UUID] = _uuid_col("companies.id")
    invoice_number: Mapped[str | None] = mapped_column(String(64), index=True)
    allocated_liters: Mapped[float] = mapped_column(Float, nullable=False)
    dispensed_liters: Mapped[float] = mapped_column(Float, default=0.0)
    remaining_liters: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", index=True)

    employee: Mapped["Employee"] = relationship(  # noqa: F821
        back_populates="allocations", lazy="selectin"
    )
    codes: Mapped[list["DispenseCode"]] = relationship(back_populates="allocation")


class DispenseCode(TimestampMixin, Base):
    """Single-use authorization code.

    Stores:
      * ``code_hash`` – salted PBKDF2-SHA256 hash (at-rest secret; what the
        pipeline phone number holder must never see re-derived).
      * ``code_fp``   – deterministic HMAC-SHA256 fingerprint used for O(log N)
        indexed lookups from the station/RPi without leaking the code.
    """

    __tablename__ = "dispense_codes"

    id: Mapped[uuid_type.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_type.uuid4
    )
    allocation_id: Mapped[uuid_type.UUID] = _uuid_col("allocations.id")
    code_hash: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    code_fp: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    code_length: Mapped[int] = mapped_column(Integer, default=6)
    authorized_liters: Mapped[float] = mapped_column(Float, nullable=False)
    consumed_liters: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", index=True)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    allocation: Mapped["Allocation"] = relationship(back_populates="codes")


class DispenseTransaction(TimestampMixin, Base):
    """Records a completed (or attempted) dispense at a station."""

    __tablename__ = "dispense_transactions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    station_id: Mapped[uuid_type.UUID] = _uuid_col("stations.id")
    dispenser_id: Mapped[uuid_type.UUID] = _uuid_col("dispensers.id")
    code_id: Mapped[uuid_type.UUID] = _uuid_col("dispense_codes.id")
    employee_id: Mapped[uuid_type.UUID] = _uuid_col("employees.id")
    allocation_id: Mapped[uuid_type.UUID] = _uuid_col("allocations.id")
    requested_liters: Mapped[float] = mapped_column(Float, nullable=False)
    actual_liters: Mapped[float] = mapped_column(Float, nullable=False)
    secret_totalizer_before: Mapped[int] = mapped_column(BigInteger, default=0)
    secret_totalizer_after: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[str] = mapped_column(String(32), default="COMPLETED")
    notes: Mapped[str | None] = mapped_column(Text)


class StationTotalizer(TimestampMixin, Base):
    """Point-in-time reading of the hardware secret counter meter."""

    __tablename__ = "station_totalizers"
    __table_args__ = (PrimaryKeyConstraint("id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), nullable=False)
    station_id: Mapped[uuid_type.UUID] = _uuid_col("stations.id")
    dispenser_id: Mapped[uuid_type.UUID] = _uuid_col("dispensers.id")
    totalizer_value: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cumulative_liters: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="hardware")  # hardware|backfill|manual