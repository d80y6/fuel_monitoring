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
    assert mid < 200.0, "cubic spline must not degenerate to linear"
    assert mid == pytest.approx(188.75, abs=1.0)  # smooth, not linear (200)


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


def test_cubic_spline_clamps_outside_domain():
    points = [(0.0, 0.0), (1.0, 100.0)]
    assert interpolate_strapping(points, 5.0, "cubic_spline") == 100.0
    assert interpolate_strapping(points, -1.0, "cubic_spline") == 0.0


def test_unknown_method_raises_value_error():
    points = [(0.0, 0.0), (1.0, 100.0)]
    with pytest.raises(ValueError):
        interpolate_strapping(points, 0.5, "bogus")


def test_duplicate_heights_raise_value_error():
    points = [(0.0, 0.0), (1.0, 100.0), (1.0, 100.0), (2.0, 250.0)]
    with pytest.raises(ValueError, match="strictly increasing"):
        interpolate_strapping(points, 1.0, "cubic_spline")
