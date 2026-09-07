# platform/fmp/tests/unit/test_tank_geometry.py
"""Unit tests for tank geometry: cubic spline + strapping interpolation + shapes."""
from __future__ import annotations

import math

import pytest

from fmp.ingestion.tank_geometry import (
    calculate_volume_for_shape,
    interpolate_strapping,
)


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


# --------------------------------------------------------------------------
# shape-aware volume engine
# --------------------------------------------------------------------------
def test_vertical_cylinder_volume():
    v = calculate_volume_for_shape(1.0, "vertical_cylinder", diameter=1.5, height=2.0)
    assert v == pytest.approx(math.pi * 0.75**2 * 1.0 * 1000, rel=1e-6)


def test_horizontal_cylinder_half_full():
    full = calculate_volume_for_shape(1.5, "horizontal_cylinder", diameter=1.5, length=2.0)
    half = calculate_volume_for_shape(0.75, "horizontal_cylinder", diameter=1.5, length=2.0)
    assert half == pytest.approx(full / 2, rel=0.001)


def test_rectangular_tank_volume():
    v = calculate_volume_for_shape(
        0.5, "rectangular", width=1.0, length=2.0, height=1.5
    )
    assert v == pytest.approx(0.5 * 1.0 * 2.0 * 1000)


def test_spherical_tank_full_volume():
    r = 1.0  # m; full sphere volume = 4/3 pi r^3
    full = calculate_volume_for_shape(2.0, "spherical", diameter=2.0)
    assert full == pytest.approx((4 / 3) * math.pi * r**3 * 1000, rel=1e-4)


def test_spherical_tank_half_volume():
    full = calculate_volume_for_shape(2.0, "spherical", diameter=2.0)
    half = calculate_volume_for_shape(1.0, "spherical", diameter=2.0)
    assert half == pytest.approx(full / 2, rel=0.01)


def test_custom_strapping_cubic_dispatch():
    points = [(0.0, 0.0), (1.0, 100.0), (2.0, 250.0)]
    v = calculate_volume_for_shape(
        1.5, "custom_strapping", strapping={"points": points, "method": "cubic_spline"}
    )
    assert v == pytest.approx(interpolate_strapping(points, 1.5, "cubic_spline"))


def test_horizontal_elliptical_ends_exceed_plain_cylinder():
    # Two full elliptical heads (half-ellipsoids, semi-axes r, r, dish) hold
    # 2 * (2/3) * pi * r^2 * dish each => (4/3) * pi * r^2 * dish total.
    plain = calculate_volume_for_shape(1.5, "horizontal_cylinder", diameter=1.5, length=2.0)
    head = calculate_volume_for_shape(
        1.5, "horizontal_elliptical_ends", diameter=1.5, length=2.0, dish_depth=0.4
    )
    assert head > plain
    assert head == pytest.approx(
        plain + (4 / 3) * math.pi * (0.75**2) * 0.4 * 1000, rel=0.05
    )


def test_unknown_shape_rejected():
    with pytest.raises(ValueError):
        calculate_volume_for_shape(1.0, "tesseract", diameter=1.0)
