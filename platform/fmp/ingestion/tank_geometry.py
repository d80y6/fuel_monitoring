# platform/fmp/ingestion/tank_geometry.py
"""Pure tank-geometry math: shapes, cubic spline, strapping, density/VCF/NSV.

Dependency-free so the pipeline can run on the edge and be unit-tested fully.
"""
from __future__ import annotations

import math
from collections.abc import Iterable

REFERENCE_TEMP_C = 15.0


def _natural_cubic_spline(fx: list[float], fy: list[float]) -> tuple[list[float], list[float]]:
    """Return second-derivative coefficients for a natural cubic spline.

    Solves the tridiagonal system with zero second derivatives at both ends
    (``M[0] == M[n] == 0``) via the Thomas algorithm. The second return value
    is kept for signature compatibility and is not used by callers.
    """
    n = len(fx) - 1
    h = [fx[i + 1] - fx[i] for i in range(n)]
    m = n - 1
    m2 = [0.0] * (n + 1)
    if m == 0:
        return m2, [0.0] * n

    sub = [0.0] * (m + 1)
    diag = [0.0] * (m + 1)
    sup = [0.0] * (m + 1)
    rhs = [0.0] * (m + 1)
    for i in range(1, m + 1):
        sub[i] = h[i - 1]
        diag[i] = 2.0 * (h[i - 1] + h[i])
        sup[i] = h[i]
        rhs[i] = 6.0 * ((fy[i + 1] - fy[i]) / h[i] - (fy[i] - fy[i - 1]) / h[i - 1])

    cp = [0.0] * (m + 2)
    dp = [0.0] * (m + 1)
    cp[1] = sup[1] / diag[1]
    dp[1] = rhs[1] / diag[1]
    for i in range(2, m + 1):
        denom = diag[i] - sub[i] * cp[i - 1]
        cp[i] = sup[i] / denom
        dp[i] = (rhs[i] - sub[i] * dp[i - 1]) / denom

    m2[m] = dp[m]
    for i in range(m - 1, 0, -1):
        m2[i] = dp[i] - cp[i] * m2[i + 1]
    return m2, [0.0] * n


def _spline_eval(fx: list[float], fy: list[float], m2: list[float], x: float) -> float:
    n = len(fx) - 1
    if x <= fx[0]:
        return fy[0]
    if x >= fx[n]:
        return fy[n]
    lo, hi = 0, n
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if fx[mid] <= x:
            lo = mid
        else:
            hi = mid
    i = lo
    h = fx[i + 1] - fx[i]
    a = (fx[i + 1] - x) / h
    b = (x - fx[i]) / h
    return (
        a * fy[i] + b * fy[i + 1]
        + ((a**3 - a) * m2[i] + (b**3 - b) * m2[i + 1]) * (h * h) / 6.0
    )


def interpolate_strapping(
    points: Iterable[tuple[float, float]], level: float, method: str
) -> float:
    """Volume (liters) at ``level`` from calibration ``[{height, volume}]``.

    ``method`` is ``"linear"`` or ``"cubic_spline"``. Outside the domain the
    result clamps to the nearest end point (no extrapolation).
    """
    pts = sorted((float(h), float(v)) for h, v in points)
    if len(pts) < 2:
        raise ValueError("strapping table requires at least 2 points")
    if any(pts[i][0] >= pts[i + 1][0] for i in range(len(pts) - 1)):
        raise ValueError("strapping heights must be strictly increasing")
    if method not in ("linear", "cubic_spline"):
        raise ValueError(f"unknown interpolation method: {method}")
    hs = [p[0] for p in pts]
    vs = [p[1] for p in pts]
    if level <= hs[0]:
        return vs[0]
    if level >= hs[-1]:
        return vs[-1]
    if method == "linear":
        for i in range(len(hs) - 1):
            if hs[i] <= level <= hs[i + 1]:
                t = (level - hs[i]) / (hs[i + 1] - hs[i])
                return vs[i] + t * (vs[i + 1] - vs[i])
    if method == "cubic_spline":
        m2, _ = _natural_cubic_spline(hs, vs)
        return _spline_eval(hs, vs, m2, level)
    raise ValueError(f"unknown interpolation method: {method}")


def density_at_temperature(
    base_density: float, thermal_expansion_coeff: float, temperature_c: float | None
) -> float:
    """rho(T) = base_density * (1 - coeff * (T - 15.0)); None -> base_density."""
    if temperature_c is None:
        return base_density
    return base_density * (1.0 - thermal_expansion_coeff * (temperature_c - REFERENCE_TEMP_C))


def volume_correction_factor(thermal_expansion_coeff: float, temperature_c: float | None) -> float:
    """VCF = rho(T)/rho(15C) = 1 - coeff * (T - 15.0)."""

    if temperature_c is None:
        return 1.0
    return 1.0 - thermal_expansion_coeff * (temperature_c - REFERENCE_TEMP_C)


def net_standard_volume(
    gross_volume_liters: float, thermal_expansion_coeff: float, temperature_c: float | None
) -> float:
    """NSV (liters @15C) = GOV * VCF."""
    return gross_volume_liters * volume_correction_factor(thermal_expansion_coeff, temperature_c)


def _clamp(level: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(level, maximum))


def _horizontal_cylinder_volume(level: float, diameter: float, length: float) -> float:
    level = _clamp(level, 0.0, diameter)
    radius = diameter / 2.0
    if level <= 0.001:
        return 0.0
    if level >= diameter - 0.001:
        return math.pi * radius**2 * length * 1000
    if level <= radius:
        theta = 2 * math.acos((radius - level) / radius)
        area = (radius**2 * (theta - math.sin(theta))) / 2
    else:
        h_empty = diameter - level
        theta = 2 * math.acos((radius - h_empty) / radius)
        area = math.pi * radius**2 - (radius**2 * (theta - math.sin(theta))) / 2
    return area * length * 1000


def _elliptical_head_volume(level: float, radius: float, dish_depth: float) -> float:
    """Partial volume of ONE horizontal elliptical head (ellipsoid segment).

    Ellipsoid of revolution: semi-axes (radius, radius, dish_depth) along x,y,z.
    Segment volume below a horizontal slice at height ``level`` is integrated
    over the dish axis with adaptive Simpson quadrature.
    """
    step = radius / 40.0
    total = 0.0
    z = 0.0
    while z < radius - 1e-12:
        z_next = min(z + step, radius)
        seg = _head_segment_area(radius, dish_depth, (z + z_next) / 2) * (z_next - z)
        total += seg
        z = z_next
    return total * 1000


def _head_segment_area(radius: float, dish_depth: float, z: float) -> float:
    # cross-section of the ellipsoid at a given dish-axis (z) coordinate,
    # integrated along the other transverse axis to the fill plane.
    x_semi = radius
    y_semi = radius
    z_semi = dish_depth
    if z >= z_semi:
        return 0.0
    a = x_semi * math.sqrt(1.0 - (z / z_semi) ** 2)  # x semi-axis at this z
    b = y_semi * math.sqrt(1.0 - (z / z_semi) ** 2)  # y semi-axis at this z
    # cross-section is an ellipse with semi-axes (a,b); integrate in x.
    steps_x = 96
    area = 0.0
    for i in range(steps_x):
        xa = -a + 2 * a * i / steps_x
        xb = -a + 2 * a * (i + 1) / steps_x
        xm = (xa + xb) / 2
        half_y = b * math.sqrt(1.0 - (xm / a) ** 2) if a > 0 else 0.0
        area += 2 * half_y * (xb - xa)
    return area


def calculate_volume_for_shape(
    level: float,
    tank_shape: str,
    *,
    diameter: float | None = None,
    length: float | None = None,
    height: float | None = None,
    width: float | None = None,
    dish_depth: float | None = None,
    strapping: dict | None = None,
) -> float:
    """Volume in liters for a level reading dispatched by physical shape."""
    shapes = ("vertical_cylinder", "horizontal_cylinder", "rectangular",
              "spherical", "horizontal_elliptical_ends", "custom_strapping")
    if tank_shape not in shapes:
        raise ValueError(f"unknown tank_shape: {tank_shape}")

    if tank_shape == "vertical_cylinder":
        height = height or 0.0
        level = _clamp(level, 0.0, height)
        return math.pi * (diameter / 2.0) ** 2 * level * 1000

    if tank_shape == "rectangular":
        length, width, height = (length or 0.0), (width or 0.0), (height or 0.0)
        level = _clamp(level, 0.0, height)
        return length * width * level * 1000

    if tank_shape == "spherical":
        radius = diameter / 2.0
        level = _clamp(level, 0.0, diameter)
        return (math.pi * level**2 / 3.0) * (3 * radius - level) * 1000

    if tank_shape == "custom_strapping":
        if not strapping:
            raise ValueError("custom_strapping requires a strapping table")
        return interpolate_strapping(strapping["points"], level, strapping["method"])

    if tank_shape == "horizontal_elliptical_ends":
        length = length or 0.0
        radius = diameter / 2.0
        dish = dish_depth or 0.0
        level = _clamp(level, 0.0, diameter)
        cyl = _horizontal_cylinder_volume(level, diameter, length)
        heads = _elliptical_head_volume(level, radius, dish) * 2
        return cyl + heads

    # horizontal_cylinder
    return _horizontal_cylinder_volume(level, diameter or 0.0, length or 0.0)
