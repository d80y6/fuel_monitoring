"""ORMs: Tank and Alarm (storage telemetry domain)."""
from __future__ import annotations

import uuid as uuid_type
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, PrimaryKeyConstraint, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fmp.core.database import Base
from fmp.models.base import (
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

if TYPE_CHECKING:
    from fmp.models.fuel import FuelType
    from fmp.models.gateway import IoTGateway

TANK_ORIENTATIONS = ("vertical", "horizontal")


class Tank(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A fuel storage tank instrumented with a pressure/temperature sensor."""

    __tablename__ = "tanks"

    name: Mapped[str] = mapped_column(String(100), index=True)
    site_id: Mapped[uuid_type.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id"), index=True
    )
    gateway_id: Mapped[uuid_type.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iot_gateways.id"), index=True
    )
    gateway_mac: Mapped[str | None] = mapped_column(String(17), index=True)
    sensor_serial_number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    device_address: Mapped[int] = mapped_column(Integer, default=1)

    tank_orientation: Mapped[str] = mapped_column(String(20), default="vertical")
    tank_height: Mapped[float | None] = mapped_column(Float)
    tank_diameter: Mapped[float] = mapped_column(Float)
    tank_length: Mapped[float | None] = mapped_column(Float)
    tank_volume: Mapped[float] = mapped_column(Float)
    tank_shape: Mapped[str] = mapped_column(String(20), default="vertical_cylinder")
    dish_depth: Mapped[float | None] = mapped_column(Float)
    tank_width: Mapped[float | None] = mapped_column(Float)
    fuel_type_id: Mapped[uuid_type.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fuel_types.id"), index=True
    )
    strapping_table_id: Mapped[uuid_type.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("strapping_tables.id", name="fk_tanks_strapping_table_id"),
        index=True,
    )
    elevation: Mapped[float | None] = mapped_column(Float)
    calibration_factor: Mapped[float] = mapped_column(Float, default=1.0)
    atmospheric_pressure: Mapped[float] = mapped_column(Float, default=0.0)

    low_level_threshold: Mapped[float | None] = mapped_column(Float)
    critical_level_threshold: Mapped[float | None] = mapped_column(Float)
    high_level_threshold: Mapped[float | None] = mapped_column(Float)
    low_volume_threshold: Mapped[float | None] = mapped_column(Float)
    high_volume_threshold: Mapped[float | None] = mapped_column(Float)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    connection_status: Mapped[str] = mapped_column(String(20), default="offline")
    last_connection: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    site: Mapped["Site"] = relationship(back_populates="tanks")  # noqa: F821
    gateway: Mapped["IoTGateway"] = relationship(back_populates="tanks")  # noqa: F821
    alarms: Mapped[list["Alarm"]] = relationship(
        back_populates="tank", cascade="all, delete-orphan"
    )
    fuel_type: Mapped["FuelType"] = relationship(lazy="selectin")  # noqa: F821

    @property
    def total_capacity_liters(self) -> float:
        return self.tank_volume


class Alarm(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "alarms"

    tank_id: Mapped[uuid_type.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tanks.id"), index=True
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    type: Mapped[str] = mapped_column(String(40))
    level: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(Text)
    value: Mapped[float] = mapped_column(Float, nullable=True)

    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledged_by: Mapped[uuid_type.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    tank: Mapped["Tank"] = relationship(back_populates="alarms")


class Measurement(Base):
    """Timeseries row (a TimescaleDB hypertable candidate).

    The composite primary key includes the partitioning column so the table can
    be promoted to a hypertable (TimescaleDB requires every unique index to
    contain the dimension column).
    """

    __tablename__ = "measurements"
    __table_args__ = (PrimaryKeyConstraint("tank_id", "timestamp"),)

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    tank_id: Mapped[uuid_type.UUID] = mapped_column(UUID(as_uuid=True))
    pressure: Mapped[float] = mapped_column(Float)
    temperature: Mapped[float | None] = mapped_column(Float)
    level: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)
    flow_rate: Mapped[float | None] = mapped_column(Float)
    gov_volume: Mapped[float | None] = mapped_column(Float)
    net_volume: Mapped[float | None] = mapped_column(Float)
    density_at_temperature: Mapped[float | None] = mapped_column(Float)
    fill_percent: Mapped[float | None] = mapped_column(Float)
    status: Mapped[int] = mapped_column(Integer, default=0)
    is_outlier: Mapped[bool] = mapped_column(Boolean, default=False)