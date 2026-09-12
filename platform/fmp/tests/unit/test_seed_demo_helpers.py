# platform/fmp/tests/unit/test_seed_demo_helpers.py
"""Unit tests for the demo-seed data generation helpers (pure logic only)."""
from __future__ import annotations

import pytest

from fmp.scripts.seed_demo import (
    HOURS_PER_DAY,
    SEED_DAYS,
    _build_measurement_rows,
    _hourly_volumes,
    _level_volume,
    _pressure_bar,
)


def test_level_volume_vertical_cylinder():
    level, volume = _level_volume(10000.0, 3.0, 50.0)
    assert volume == 5000.0
    assert level == 1.5
    level, volume = _level_volume(10000.0, 3.0, 100.0)
    assert volume == 10000.0
    assert level == 3.0


def test_pressure_bar_scales_with_level_and_density():
    p = _pressure_bar(2.0, 845.0)
    expected = 2.0 * 845.0 * 9.81 / 1e5
    assert p == round(expected, 4)


def test_hourly_volumes_cover_full_days_plus_closing_sample():
    vols = _hourly_volumes(SEED_DAYS)
    assert len(vols) == SEED_DAYS * HOURS_PER_DAY + 1


def test_hourly_volumes_are_in_positive_range_and_deterministic():
    v1 = _hourly_volumes(SEED_DAYS)
    v2 = _hourly_volumes(SEED_DAYS)
    assert v1 == v2, "fixed-seed generator must be reproducible"
    assert all(0.0 < v <= 10000.0 for v in v1)


def test_measurement_rows_have_consistent_fields():
    class _FakeTank:
        id = "00000000-0000-0000-0000-000000000001"
        tank_volume = 10000.0
        tank_height = 3.0

    rows = _build_measurement_rows(_FakeTank(), 845.0)
    assert len(rows) == SEED_DAYS * HOURS_PER_DAY + 1
    for row in rows:
        assert row["volume"] == pytest.approx(
            row["fill_percent"] / 100.0 * 10000.0, abs=0.6
        )
        assert row["level"] > 0.0
        assert row["level"] <= 3.0
        assert row["temperature"] == round(row["temperature"], 1)
        assert row["status"] == 0
        assert row["is_outlier"] is False