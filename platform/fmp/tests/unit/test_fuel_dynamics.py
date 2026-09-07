# platform/fmp/tests/unit/test_fuel_dynamics.py
"""Unit tests for fuel density, VCF and NSV math."""
from __future__ import annotations

import pytest

from fmp.ingestion.tank_geometry import density_at_temperature, net_standard_volume, volume_correction_factor


def test_density_at_reference_temp_equals_base():
    assert density_at_temperature(845.0, 0.0008, 15.0) == pytest.approx(845.0)


def test_density_drops_when_hotter():
    d = density_at_temperature(845.0, 0.0008, 35.0)
    assert d == pytest.approx(845.0 * (1 - 0.0008 * (35 - 15)), rel=1e-9)


def test_density_rises_when_colder():
    d = density_at_temperature(750.0, 0.00095, 5.0)
    assert d == pytest.approx(750.0 * (1 - 0.00095 * (5 - 15)), rel=1e-9)


def test_density_without_temperature_returns_base():
    assert density_at_temperature(800.0, 0.0009, None) == pytest.approx(800.0)


def test_vcf_is_linear_in_temperature():
    assert volume_correction_factor(0.0008, 25.0) == pytest.approx(1 - 0.0008 * (25 - 15))
    assert volume_correction_factor(0.0008, 15.0) == pytest.approx(1.0)


def test_vcf_without_temperature_returns_one():
    assert volume_correction_factor(0.0008, None) == pytest.approx(1.0)


def test_nsv_without_temperature_returns_gov():
    assert net_standard_volume(1000.0, 0.0008, None) == pytest.approx(1000.0)


def test_nsv_equals_gov_times_vcf():
    gov = 1000.0
    nsv = net_standard_volume(gov, 0.0008, 35.0)
    assert nsv == pytest.approx(gov * (1 - 0.0008 * (35 - 15)))
