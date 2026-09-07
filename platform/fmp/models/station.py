"""ORMs: Company, Site, Station, Dispenser, Employee (organizational core)."""
from __future__ import annotations

import uuid as uuid_type
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fmp.models.base import (
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from fmp.core.database import Base


class Company(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    address: Mapped[str | None] = mapped_column(String(255))
    contact_name: Mapped[str | None] = mapped_column(String(100))
    contact_email: Mapped[str | None] = mapped_column(String(120))
    contact_phone: Mapped[str | None] = mapped_column(String(20))

    sites: Mapped[list["Site"]] = relationship(back_populates="company")
    employees: Mapped[list["Employee"]] = relationship(back_populates="company")


class Site(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "sites"

    name: Mapped[str] = mapped_column(String(100), index=True)
    company_id: Mapped[uuid_type.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id")
    )
    address: Mapped[str | None] = mapped_column(String(255))
    location: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    company: Mapped["Company"] = relationship(back_populates="sites")
    stations: Mapped[list["Station"]] = relationship(back_populates="site")
    tanks: Mapped[list["Tank"]] = relationship(back_populates="site")  # noqa: F821


class Station(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "stations"

    name: Mapped[str] = mapped_column(String(100), index=True)
    site_id: Mapped[uuid_type.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id")
    )
    serial_number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    raspberry_pi_id: Mapped[str | None] = mapped_column(String(64), index=True)
    firmware_version: Mapped[str | None] = mapped_column(String(32))
    connection_status: Mapped[str] = mapped_column(String(20), default="offline")
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    site: Mapped["Site"] = relationship(back_populates="stations")
    dispensers: Mapped[list["Dispenser"]] = relationship(back_populates="station")


class Dispenser(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "dispensers"

    name: Mapped[str] = mapped_column(String(100))
    station_id: Mapped[uuid_type.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stations.id")
    )
    serial_number: Mapped[str] = mapped_column(String(64), unique=True)
    modbus_address: Mapped[int] = mapped_column(default=1)
    dispenser_model: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    station: Mapped["Station"] = relationship(back_populates="dispensers")


class Employee(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "employees"

    employee_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(20), index=True)
    email: Mapped[str | None] = mapped_column(String(120))
    company_id: Mapped[uuid_type.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    company: Mapped["Company"] = relationship(back_populates="employees")
    allocations: Mapped[list["Allocation"]] = relationship(  # noqa: F821
        back_populates="employee"
    )