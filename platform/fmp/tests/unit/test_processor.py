"""Unit tests for the telemetry ingestion processor (pure physics + anomaly).

All cases are hand-computed; no infrastructure required.
"""
from __future__ import annotations

import math

import pytest

from fmp.ingestion.processor import (
    EMA,
    MADAnomalyDetector,
    calculate_volume,
    elevation_compensated_gravity,
    fill_percent,
    pressure_to_level,
)


# --------------------------------------------------------------------------
# pressure -> level
# --------------------------------------------------------------------------
def test_pressure_to_level_uses_hydrostatic_formula():
    # P = rho * g * h  =>  h = P / (rho * g)
    # density 840 kg/m3, g=9.80665, elevation 0 => level 1.0 m  -> 8.2376 kPa = 0.08238 bar
    level = pressure_to_level(
        pressure_bar=0.082376, atmospheric_bar=0.0,
        density=840.0, elevation=0.0, calibration_factor=1.0,
    )
    assert level == pytest.approx(1.0, abs=0.001)


def test_pressure_to_level_applies_calibration_factor():
    level = pressure_to_level(
        pressure_bar=0.082376, atmospheric_bar=0.0,
        density=840.0, elevation=0.0, calibration_factor=1.05,
    )
    assert level == pytest.approx(1.05, abs=0.001)


def test_pressure_to_level_handles_elevation_gravity_correction():
    g = elevation_compensated_gravity(1000.0)
    assert g == pytest.approx(9.80665 - 3.086e-6 * 1000.0)


# --------------------------------------------------------------------------
# volume
# --------------------------------------------------------------------------
def test_vertical_tank_volume():
    # r=0.75m, level 1.0m => pi*0.75^2*1.0 m3 = 1767.146 L
    vol = calculate_volume(
        level=1.0, orientation="vertical",
        tank_diameter=1.5, tank_length=2.0,
    )
    assert vol == pytest.approx(math.pi * 0.75**2 * 1.0 * 1000, abs=0.1)


def test_vertical_tank_level_clamped_to_tank_height():
    # height 2.0 m (raw reading 5.0 m) => uses 2.0 m, length irrelevant for vertical
    vol = calculate_volume(
        level=5.0, orientation="vertical",
        tank_diameter=1.5, tank_length=None, tank_height=2.0,
    )
    assert vol == pytest.approx(math.pi * 0.75**2 * 2.0 * 1000, abs=0.1)


def test_horizontal_tank_half_full_equals_half_capacity():
    # 50% fill of a horizontal cylinder == half of full volume
    full = calculate_volume(
        level=1.5, orientation="horizontal",
        tank_diameter=1.5, tank_length=2.0,
    )
    half = calculate_volume(
        level=0.75, orientation="horizontal",
        tank_diameter=1.5, tank_length=2.0,
    )
    assert half == pytest.approx(full / 2, rel=0.001)


def test_horizontal_tank_full_volume():
    full = calculate_volume(
        level=1.5, orientation="horizontal",
        tank_diameter=1.5, tank_length=2.0,
    )
    assert full == pytest.approx(math.pi * 0.75**2 * 2.0 * 1000, abs=0.1)


# --------------------------------------------------------------------------
# fill percent
# --------------------------------------------------------------------------
def test_fill_percent_bounds():
    assert fill_percent(500.0, 1000.0) == pytest.approx(50.0)
    assert fill_percent(0.0, 1000.0) == 0.0
    assert fill_percent(1500.0, 1000.0) == 100.0
    assert fill_percent(0.0, 0.0) == 0.0


# --------------------------------------------------------------------------
# EMA
# --------------------------------------------------------------------------
def test_ema_initialises_to_first_sample():
    ema = EMA(span=5)
    ema.update(10.0)
    assert ema.value == pytest.approx(10.0)


def test_ema_constant_series_stays_constant():
    ema = EMA(span=5)
    for _ in range(20):
        ema.update(42.0)
    assert ema.value == pytest.approx(42.0)


def test_ema_converges_towards_new_level():
    ema = EMA(span=5)
    for i in range(5):
        ema.update(10.0 + i)
    assert ema.value == pytest.approx(12.0, abs=0.5)


# --------------------------------------------------------------------------
# MAD Z-score anomaly detector
# --------------------------------------------------------------------------
def test_mad_flags_clear_outlier_after_warmup():
    detector = MADAnomalyDetector(window=6, threshold=3.5)
    samples = [10.0, 11.0, 10.0, 12.0, 10.0]
    for s in samples:
        assert detector.update(s) is False
    # big jump: should be flagged
    assert detector.update(100.0) is True


def test_mad_not_flag_steady_stream():
    detector = MADAnomalyDetector(window=6, threshold=3.5)
    for _ in range(30):
        assert detector.update(10.0) is False


def test_mad_needs_warmup_before_detection():
    detector = MADAnomalyDetector(window=5, threshold=3.5)
    assert detector.update(100.0) is False  # insufficient history