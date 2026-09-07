"""Unit tests for FuelType/StrappingTable ORM definitions (no DB)."""
from __future__ import annotations

import pytest

from fmp.models import FuelType, StrappingTable, Tank


def test_new_models_registered():
    assert hasattr(FuelType, "code")
    assert hasattr(StrappingTable, "calibration_data")
    assert hasattr(StrappingTable, "interpolation_method")


def test_tank_gains_fuel_and_shape_fields():
    assert hasattr(Tank, "tank_shape")
    assert hasattr(Tank, "fuel_type_id")
    assert hasattr(Tank, "dish_depth")
    assert hasattr(Tank, "tank_width")
    assert not hasattr(Tank, "fluid_density")


def test_measurement_gains_gov_nsv_fields():
    from fmp.models import Measurement

    assert hasattr(Measurement, "gov_volume")
    assert hasattr(Measurement, "net_volume")
    assert hasattr(Measurement, "density_at_temperature")


def test_strapping_json_default_factory():
    s = StrappingTable(interpolation_method="linear")
    assert s.calibration_data == []