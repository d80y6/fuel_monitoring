"""Fuel domain models: fuel types + strapping tables."""
from __future__ import annotations

import uuid as uuid_type

from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column

from fmp.core.database import Base
from fmp.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class FuelType(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Fuel physical properties; the single source of truth for density."""

    __tablename__ = "fuel_types"

    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64))
    base_density: Mapped[float] = mapped_column(Float)          # kg/m3 @15C
    thermal_expansion_coeff: Mapped[float] = mapped_column(Float)  # 1/C
    max_vapor_pressure: Mapped[float] = mapped_column(Float)    # kPa
    viscosity_cst: Mapped[float] = mapped_column(Float)         # cSt


class StrappingTable(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Calibration height->volume array for a tank (custom strapping)."""

    __tablename__ = "strapping_tables"

    tank_id: Mapped[uuid_type.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tanks.id", name="fk_strapping_tables_tank_id"),
        unique=True,
        index=True,
    )
    calibration_data: Mapped[list] = mapped_column(
        MutableList.as_mutable(JSONB), default=list
    )
    interpolation_method: Mapped[str] = mapped_column(String(20), default="linear")

    def __init__(self, **kwargs: object) -> None:
        self.calibration_data = kwargs.pop("calibration_data", [])
        super().__init__(**kwargs)