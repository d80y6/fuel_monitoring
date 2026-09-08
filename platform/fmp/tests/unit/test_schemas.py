"""Unit tests for new Pydantic schemas."""
from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from fmp.schemas.fuel import FuelTypeCreate, FuelTypeRead
from fmp.schemas.strapping import StrappingTableUpsert, StrappingTableRead
from fmp.schemas.tanks import TankCreate


def test_fuel_schema_roundtrip():
    f = FuelTypeCreate(code="gasoline", name="Gasoline", base_density=750.0,
                       thermal_expansion_coeff=0.00095, max_vapor_pressure=60.0,
                       viscosity_cst=0.6)
    out = FuelTypeRead.model_validate({"id": uuid.uuid4(), **f.model_dump(),
                                       "created_at": "2026-01-01T00:00:00Z"})
    assert out.code == "gasoline"


def test_strapping_schema_requires_two_points():
    with pytest.raises(ValidationError):
        StrappingTableUpsert(calibration_data=[{"height": 0.0, "volume": 0.0}],
                             interpolation_method="linear")


def test_tank_create_requires_fuel_type_and_shape():
    with pytest.raises(ValidationError):
        TankCreate(
            name="t", site_id=uuid.uuid4(), sensor_serial_number="sn-1",
            tank_diameter=1.0, tank_volume=100.0,
            # fuel_type_id intentionally missing
        )


def test_tank_shape_orientation_consistency():
    with pytest.raises(ValidationError):
        TankCreate(
            name="t", site_id=uuid.uuid4(), sensor_serial_number="sn-2",
            fuel_type_id=uuid.uuid4(), tank_orientation="horizontal",
            tank_shape="vertical_cylinder", tank_diameter=1.0, tank_height=2.0,
            tank_volume=100.0,
        )


def test_custom_strapping_requires_table():
    with pytest.raises(ValidationError):
        TankCreate(
            name="t", site_id=uuid.uuid4(), sensor_serial_number="sn-3",
            fuel_type_id=uuid.uuid4(), tank_orientation="vertical",
            tank_shape="custom_strapping", tank_diameter=1.0, tank_height=2.0,
            tank_volume=100.0,
        )
