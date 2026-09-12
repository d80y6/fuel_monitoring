"""Analytics store: persisted daily consumption summaries per tank.

Written by the Celery analytics task (``analytics.compute_daily_consumption`` /
``analytics.compute_all_consumption``) so consumption history and its SMA
forecast accumulate at a fixed cadence and can be audited post-hoc.
"""
from __future__ import annotations

import uuid as uuid_type
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from fmp.core.database import Base
from fmp.models.base import UUIDPrimaryKeyMixin


class ConsumptionSummary(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "consumption_summaries"
    __table_args__ = (
        UniqueConstraint("tank_id", "day", name="uq_consumption_tank_day"),
    )

    tank_id: Mapped[uuid_type.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tanks.id"), index=True
    )
    day: Mapped[date] = mapped_column(Date, index=True)
    liters: Mapped[float] = mapped_column(Float)
    forecast_liters_per_day: Mapped[float | None] = mapped_column(Float)
    forecast_window_days: Mapped[int | None] = mapped_column(Integer)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )