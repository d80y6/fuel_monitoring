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


def _spline_eval(fx, fy, m2, x: float) -> float:
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
        return vs[0]
    if method == "cubic_spline":
        m2, _ = _natural_cubic_spline(hs, vs)
        return _spline_eval(hs, vs, m2, level)
    raise ValueError(f"unknown interpolation method: {method}")
