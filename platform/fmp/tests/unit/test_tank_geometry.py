# platform/fmp/tests/unit/test_tank_geometry.py
"""Unit tests for tank geometry: cubic spline + strapping interpolation."""
from __future__ import annotations

import pytest

from fmp.ingestion.tank_geometry import interpolate_strapping


def test_cubic_spline_passes_through_knots():
    points = [(0.0, 0.0), (1.0, 100.0), (2.0, 300.0), (3.0, 550.0)]
    for h, v in points:
        assert interpolate_strapping(points, h, "cubic_spline") == pytest.approx(v, rel=1e-9)


def test_cubic_spline_interpolates_between_knots_smoothly():
    points = [(0.0, 0.0), (1.0, 100.0), (2.0, 300.0), (3.0, 550.0)]
    mid = interpolate_strapping(points, 1.5, "cubic_spline")
    assert 100.0 < mid < 300.0
    assert mid == pytest.approx(190.0, abs=40.0)  # smooth, not linear (150)


def test_strapping_clamps_outside_domain():
    points = [(0.0, 0.0), (1.0, 100.0)]
    assert interpolate_strapping(points, -1.0, "linear") == pytest.approx(0.0)
    assert interpolate_strapping(points, 2.0, "linear") == pytest.approx(100.0)


def test_linear_strapping_interpolation():
    points = [(0.0, 0.0), (1.0, 100.0), (2.0, 250.0)]
    assert interpolate_strapping(points, 1.5, "linear") == pytest.approx(175.0)


def test_requires_at_least_two_points():
    with pytest.raises(ValueError):
        interpolate_strapping([(0.0, 0.0)], 1.0, "linear")
