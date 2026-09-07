# Fuel Dynamics Engine + GOV/NSV Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the platform's storage-telemetry engine shape-aware and fuel-aware (per-shape height→volume geometry, FuelType-driven temperature-compensated density, VCF/GOV/NSV), back it with `FuelType`/`StrappingTable` models, an Alembic migration, fuel seed data, extended schemas/routers (incl. read endpoints for the frontend), and persisted GOV/NSV on the measurement stream.

**Architecture:** Pure physics lives in a new `fmp/ingestion/tank_geometry.py` (shapes, natural cubic spline, strapping interpolation, density/VCF/NSV), re-exported through `processor.py` for backward compatibility. `FuelType`/`StrappingTable` ORMs added in `fmp/models/fuel.py`; `Tank`/`Measurement` gain columns; the pipeline resolves density via `tank.fuel_type` and persists `gov_volume`/`net_volume`/`density_at_temperature`. API: new `fuel_types` + `strapping` routers, extended tank DTOs, new dispensing read endpoints. Infrastructure wired via Async Alembic migration `0001` + idempotent seed.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 async, asyncpg, TimescaleDB (@localhost:5434), Redis (@localhost:6479), FastAPI, Pydantic v2, pytest/pytest-asyncio/httpx, Alembic.

**Test env (run all infra tests from `platform/`):**
```
POSTGRES_PORT=5434 POSTGRES_DB=fuel_test POSTGRES_USER=fuelplatform POSTGRES_PASSWORD=fuelplatform123 REDIS_PORT=6479 python3 -m pytest fmp/tests -q
```
Pure unit tests need no env vars.

---
## File Map

- Create: `platform/fmp/ingestion/tank_geometry.py` — shapes + spline + strapping + density/VCF/NSV (pure, dependency-free)
- Modify: `platform/fmp/ingestion/processor.py` — re-export geometry helpers; extend `calculate_volume` kwargs
- Create: `platform/fmp/models/fuel.py` — `FuelType`, `StrappingTable`
- Modify: `platform/fmp/models/__init__.py` — register new models
- Modify: `platform/fmp/models/tank.py` — Tank columns (`tank_shape`, `dish_depth`, `tank_width`, `fuel_type_id`, `strapping_table_id`), drop `fluid_density`, Measurement columns (`gov_volume`, `net_volume`, `density_at_temperature`), set relationships
- Create: `platform/fmp/schemas/fuel.py`, `platform/fmp/schemas/strapping.py`
- Modify: `platform/fmp/schemas/tanks.py` — TankBase/TelemetryPoint changes
- Create: `platform/fmp/schemas/dispensing_read.py` (AllocationRead, TransactionRead, EmployeeRead aggregates)
- Create: `platform/fmp/api/v1/fuel_types.py`, `platform/fmp/api/v1/strapping.py`
- Modify: `platform/fmp/api/v1/tanks.py`, `platform/fmp/api/v1/dispensing.py`, `platform/fmp/api/main.py`
- Modify: `platform/fmp/ingestion/pipeline.py`, `platform/fmp/ingestion/batch_writer.py`
- Scaffold: `platform/alembic/` (+ `alembic.ini`), migration `versions/0001_fuel_dynamics.py`
- Create: `platform/fmp/scripts/seed_fuel_types.py`; modify `platform/fmp/scripts/init_db.py`
- Tests: `platform/fmp/tests/unit/test_tank_geometry.py`, `test_fuel_dynamics.py`, `tests/integration/test_fuel_dynamics_api.py`, `test_dispensing_read_api.py`

---

### Task 1: Natural cubic spline (pure)

**Files:**
- Create: `platform/fmp/ingestion/tank_geometry.py`
- Test: `platform/fmp/tests/unit/test_tank_geometry.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /home/ubuntu/fuel_monitoring/platform && python3 -m pytest fmp/tests/unit/test_tank_geometry.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'fmp.ingestion.tank_geometry'`

- [ ] **Step 3: Implement minimal module**

```python
# platform/fmp/ingestion/tank_geometry.py
"""Pure tank-geometry math: shapes, cubic spline, strapping, density/VCF/NSV.

Dependency-free so the pipeline can run on the edge and be unit-tested fully.
"""
from __future__ import annotations

import math
from collections.abc import Iterable

REFERENCE_TEMP_C = 15.0


def _natural_cubic_spline(fx: list[float], fy: list[float]) -> tuple[list[float], list[float]]:
    """Return second-derivative coefficients for a natural cubic spline."""
    n = len(fx) - 1
    b = [0.0] * (n + 1)
    u = [0.0] * n
    for i in range(1, n):
        h_i = fx[i] - fx[i - 1]
        h_ip1 = fx[i + 1] - fx[i]
        denom = 2.0 * (h_i + h_ip1)
        b[i] = (6.0 * ((fy[i + 1] - fy[i]) / h_ip1 - (fy[i] - fy[i - 1]) / h_i)) / denom
        u[i] = h_i / (h_i + h_ip1)

    w = [0.0] * (n + 1)
    for i in range(1, n):
        p = u[i] * w[i - 1] + 2.0
        w[i] = (-u[i + 1] if i < n - 1 else -1.0) / p if p else 0.0

    m2 = [0.0] * (n + 1)
    for i in range(1, n)[::-1]:
        h_i = fx[i] - fx[i - 1]
        h_ip1 = fx[i + 1] - fx[i]
        m2[i] = (b[i] - u[i] * m2[i - 1] - (u[i + 1] if i < n else 1.0) * m2[i + 1]) / 2.0

    return m2, u


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
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /home/ubuntu/fuel_monitoring/platform && python3 -m pytest fmp/tests/unit/test_tank_geometry.py -q`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add platform/fmp/ingestion/tank_geometry.py platform/fmp/tests/unit/test_tank_geometry.py
git commit -m "feat: natural cubic spline + strapping interpolation engine"
```

---

### Task 2: Fuel density + VCF + NSV math

**Files:**
- Modify: `platform/fmp/ingestion/tank_geometry.py`
- Modify: `platform/fmp/ingestion/processor.py`
- Test: `platform/fmp/tests/unit/test_fuel_dynamics.py`

- [ ] **Step 1: Write the failing tests**

```python
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
    assert d > 750.0
    assert d == pytest.approx(750.0 * (1 - 0.00095 * (5 - 15)), rel=1e-9)


def test_density_without_temperature_returns_base():
    assert density_at_temperature(800.0, 0.0009, None) == pytest.approx(800.0)


def test_vcf_is_linear_in_temperature():
    assert volume_correction_factor(0.0008, 25.0) == pytest.approx(1 - 0.0008 * (25 - 15))
    assert volume_correction_factor(0.0008, 15.0) == pytest.approx(1.0)


def test_nsv_equals_gov_times_vcf():
    gov = 1000.0
    nsv = net_standard_volume(gov, 0.0008, 35.0)
    assert nsv == pytest.approx(gov * (1 - 0.0008 * (35 - 15)))
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd /home/ubuntu/fuel_monitoring/platform && python3 -m pytest fmp/tests/unit/test_fuel_dynamics.py -q`
Expected: FAIL with `ImportError: cannot import name 'density_at_temperature'`

- [ ] **Step 3: Implement in tank_geometry.py**

Append to `platform/fmp/ingestion/tank_geometry.py`:

```python
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
```

Also add re-exports at the bottom of `platform/fmp/ingestion/processor.py`:

```python
# Re-export the fuel-dynamics helpers (kept for backward-compatible imports).
from fmp.ingestion.tank_geometry import (  # noqa: F401
    density_at_temperature,
    interpolate_strapping,
    net_standard_volume,
    volume_correction_factor,
)
```

- [ ] **Step 4: Update the legacy heuristic density test**

`platform/fmp/tests/unit/test_processor.py` currently tests the old density-range heuristic (`test_density_compensation_diesel`, `test_density_compensation_returns_base_when_near_ref`). Delete those two; they are superseded by `test_fuel_dynamics.py`. Remove the now-unused `temperature_compensated_density` import in that file. Leave `processor.temperature_compensated_density` removed from module (it is replaced by `density_at_temperature`); update any importers (checked in Task 3).

- [ ] **Step 5: Run all unit tests**

Run: `cd /home/ubuntu/fuel_monitoring/platform && python3 -m pytest fmp/tests/unit -q`
Expected: PASS. (Any import-of-`temperature_compensated_density` failures point you at callers; fix by switching them to `density_at_temperature` — the pipeline is fixed in Task 3 so run the full unit dir after Task 3 too.)

- [ ] **Step 6: Commit**

```bash
git add platform/fmp/ingestion/tank_geometry.py platform/fmp/ingestion/processor.py platform/fmp/tests/unit/test_fuel_dynamics.py platform/fmp/tests/unit/test_processor.py
git commit -m "feat: fuel density model, VCF and NSV math; drop old heuristic"
```

---

### Task 3: Shape-aware volume engine

**Files:**
- Modify: `platform/fmp/ingestion/tank_geometry.py`
- Modify: `platform/fmp/ingestion/processor.py`
- Test: `platform/fmp/tests/unit/test_tank_geometry.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `platform/fmp/tests/unit/test_tank_geometry.py`:

```python
from fmp.ingestion.tank_geometry import calculate_volume_for_shape


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
    plain = calculate_volume_for_shape(1.5, "horizontal_cylinder", diameter=1.5, length=2.0)
    head = calculate_volume_for_shape(
        1.5, "horizontal_elliptical_ends", diameter=1.5, length=2.0, dish_depth=0.4
    )
    assert head > plain
    assert head == pytest.approx(plain + math.pi * (0.75**2) * 0.4 * 1000, rel=0.05)


def test_unkown_shape_rejected():
    with pytest.raises(ValueError):
        calculate_volume_for_shape(1.0, "tesseract", diameter=1.0)
```

Also a processor-level integration check in `test_processor.py` — update `calculate_volume` calls to the new optional args and add one shape-dispatched case:

```python
def test_calculate_volume_handles_rectangular_shape():
    vol = calculate_volume(
        level=0.5, tank_shape="rectangular", orientation="vertical",
        tank_diameter=1.5, tank_length=2.0, tank_height=1.5, tank_width=1.0,
    )
    assert vol == pytest.approx(0.5 * 1.0 * 2.0 * 1000, abs=0.1)
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd /home/ubuntu/fuel_monitoring/platform && python3 -m pytest fmp/tests/unit/test_tank_geometry.py fmp/tests/unit/test_processor.py -q`
Expected: FAIL with `ImportError: cannot import name 'calculate_volume_for_shape'`

- [ ] **Step 3: Implement**

Append to `platform/fmp/ingestion/tank_geometry.py`:

```python
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
```

Extend `calculate_volume` in `platform/fmp/ingestion/processor.py` to dispatch by shape with backward-compatible defaults:

```python
def calculate_volume(
    level: float,
    orientation: str,
    tank_diameter: float,
    tank_length: float | None = None,
    tank_height: float | None = None,
    *,
    tank_shape: str | None = None,
    tank_width: float | None = None,
    dish_depth: float | None = None,
    strapping: dict | None = None,
) -> float:
    """Volume in liters from a level reading, clamped to physical dimensions.

    ``tank_shape`` dispatches the geometry (default derived from ``orientation``
    for backward compatibility: vertical -> vertical_cylinder, else horizontal).
    """
    if tank_diameter <= 0:
        return 0.0
    shape = tank_shape or ("vertical_cylinder" if orientation == "vertical" else "horizontal_cylinder")
    from fmp.ingestion.tank_geometry import calculate_volume_for_shape

    return round(
        calculate_volume_for_shape(
            level, shape,
            diameter=tank_diameter,
            length=tank_length,
            height=tank_height,
            width=tank_width,
            dish_depth=dish_depth,
            strapping=strapping,
        ),
        1,
    )
```

- [ ] **Step 4: Run to verify they pass**

Run: `cd /home/ubuntu/fuel_monitoring/platform && python3 -m pytest fmp/tests/unit/test_tank_geometry.py fmp/tests/unit/test_processor.py -q`
Expected: PASS

- [ ] **Step 5: Verify the rest of the unit layer**

Run: `cd /home/ubuntu/fuel_monitoring/platform && python3 -m pytest fmp/tests/unit -q`
Expected: PASS (existing pipeline/realtime/alarm/rules tests unaffected — pipeline updated in Task 4)

- [ ] **Step 6: Commit**

```bash
git add platform/fmp/ingestion/tank_geometry.py platform/fmp/ingestion/processor.py platform/fmp/tests/unit/test_tank_geometry.py platform/fmp/tests/unit/test_processor.py
git commit -m "feat: shape-aware volume engine (rectangular, spherical, dished ends, strapping)"
```

---

### Task 4: FuelType + StrappingTable models

**Files:**
- Create: `platform/fmp/models/fuel.py`
- Modify: `platform/fmp/models/__init__.py`
- Modify: `platform/fmp/models/tank.py`

- [ ] **Step 1: Write the failing test (model registration)**

Create `platform/fmp/tests/unit/test_fuel_models.py`:

```python
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd /home/ubuntu/fuel_monitoring/platform && python3 -m pytest fmp/tests/unit/test_fuel_models.py -q`
Expected: FAIL with `ImportError: cannot import name 'FuelType' from 'fmp.models'`

- [ ] **Step 3: Implement `fmp/models/fuel.py`**

```python
"""Fuel domain models: fuel types + strapping tables."""
from __future__ import annotations

import json
import uuid as uuid_type

from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column

from fmp.core.database import Base
from fmp.models.base import UUIDPrimaryKeyMixin, TimestampMixin


class FuelType(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Fuel physical properties; the single source of truth for density."""

    __tablename__ = "fuel_types"

    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64))
    base_density: Mapped[float] = mapped_column(Float)          # kg/m3 @15C
    thermal_expansion_coeff: Mapped[float] = mapped_column(Float)  # 1/C
    max_vapor_pressure: Mapped[float] = mapped_column(Float)    # kPa
    viscosity_cst: Mapped[float] = mapped_column(Float)         # cSt


class StrappingTable(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Calibration height->volume array for a tank (custom strapping)."""

    __tablename__ = "strapping_tables"

    tank_id: Mapped[uuid_type.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tanks.id"), unique=True, index=True
    )
    calibration_data: Mapped[list] = mapped_column(
        MutableList.as_mutable(JSONB), default=list
    )
    interpolation_method: Mapped[str] = mapped_column(String(20), default="linear")
```

- [ ] **Step 4: Register models + Tank/Measurement columns**

In `platform/fmp/models/__init__.py`, add imports and `__all__` entries for `FuelType`, `StrappingTable`.

In `platform/fmp/models/tank.py`:
- Remove the `import` usage of `Float` stays; add `from sqlalchemy.dialects.postgresql import UUID, JSONB` if needed (JSONB not needed on Tank; UUID already imported).
- Delete the `fluid_density` column.
- Add to `Tank`:

```python
    tank_shape: Mapped[str] = mapped_column(String(20), default="vertical_cylinder")
    dish_depth: Mapped[float | None] = mapped_column(Float)
    tank_width: Mapped[float | None] = mapped_column(Float)
    fuel_type_id: Mapped[uuid_type.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fuel_types.id"), index=True
    )
    strapping_table_id: Mapped[uuid_type.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("strapping_tables.id"), index=True
    )
    fuel_type: Mapped["FuelType"] = relationship(lazy="selectin")  # noqa: F821
```

- Add to `Measurement`:

```python
    gov_volume: Mapped[float | None] = mapped_column(Float)
    net_volume: Mapped[float | None] = mapped_column(Float)
    density_at_temperature: Mapped[float | None] = mapped_column(Float)
```

Add a `Tank.fuel_type` relationship target import (`from fmp.models.fuel import FuelType, StrappingTable` at top of `tank.py` — use `TYPE_CHECKING` guard if preferred; SQLAlchemy string-based forward refs resolve at mapper config via `fmp.models` import order, keep `fmp.models.tank` importable after `fmp.models.fuel`).

- [ ] **Step 5: Run to verify they pass**

Run: `cd /home/ubuntu/fuel_monitoring/platform && python3 -m pytest fmp/tests/unit/test_fuel_models.py -q`
Then import smoke: `cd /home/ubuntu/fuel_monitoring/platform && python3 -c "import fmp.models, fmp.api.main; print('imports ok')"`
Expected: PASS and "imports ok"

- [ ] **Step 6: Run full unit suite**

Run: `cd /home/ubuntu/fuel_monitoring/platform && python3 -m pytest fmp/tests/unit -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add platform/fmp/models/fuel.py platform/fmp/models/__init__.py platform/fmp/models/tank.py platform/fmp/tests/unit/test_fuel_models.py
git commit -m "feat: FuelType + StrappingTable models, tank/measurement geometry+NSV columns"
```

---

### Task 5: Schemas — fuel, strapping, tanks DTO

**Files:**
- Create: `platform/fmp/schemas/fuel.py`
- Create: `platform/fmp/schemas/strapping.py`
- Modify: `platform/fmp/schemas/tanks.py`

- [ ] **Step 1: Write failing schema tests**

Create `platform/fmp/tests/unit/test_schemas.py`:

```python
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd /home/ubuntu/fuel_monitoring/platform && python3 -m pytest fmp/tests/unit/test_schemas.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'fmp.schemas.fuel'`

- [ ] **Step 3: Implement schemas**

`platform/fmp/schemas/fuel.py`:

```python
"""Fuel type DTOs."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FuelTypeBase(BaseModel):
    code: str = Field(min_length=1, max_length=32, pattern="^[a-z0-9_]+$")
    name: str = Field(min_length=1, max_length=64)
    base_density: float = Field(gt=0)
    thermal_expansion_coeff: float = Field(gt=0)
    max_vapor_pressure: float = Field(ge=0)
    viscosity_cst: float = Field(ge=0)


class FuelTypeCreate(FuelTypeBase):
    pass


class FuelTypeRead(FuelTypeBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
```

`platform/fmp/schemas/strapping.py`:

```python
"""Strapping-table DTOs."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrappingPoint(BaseModel):
    height: float = Field(ge=0)
    volume: float = Field(ge=0)


class StrappingTableUpsert(BaseModel):
    calibration_data: list[StrappingPoint] = Field(min_length=2)
    interpolation_method: Literal["linear", "cubic_spline"] = "linear"

    @model_validator(mode="after")
    def _ascending_heights(self):
        heights = [p.height for p in self.calibration_data]
        if heights != sorted(heights):
            raise ValueError("calibration_data heights must be ascending")
        return self


class StrappingTableRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tank_id: uuid.UUID
    calibration_data: list[StrappingPoint]
    interpolation_method: Literal["linear", "cubic_spline"]
    created_at: datetime
```

Update `platform/fmp/schemas/tanks.py`:
- `TankBase`:
  - Add `TANK_SHAPES` constant and `tank_shape` field with pattern `^(vertical_cylinder|horizontal_cylinder|rectangular|spherical|horizontal_elliptical_ends|custom_strapping)$`, default `"vertical_cylinder"`.
  - Add `dish_depth: float | None = Field(default=None, gt=0)`, `tank_width: float | None = Field(default=None, gt=0)`.
  - Add `fuel_type_id: uuid.UUID` (required), `strapping_table_id: uuid.UUID | None = None`.
  - Remove `fluid_density`.
  - Keep `tank_orientation` (pattern stays `^(vertical|horizontal)$`).
  - Add a `@model_validator(mode="after")` `_shape_consistency` enforcing: `vertical_cylinder` requires orientation==vertical; `horizontal_cylinder|spherical|horizontal_elliptical_ends` require orientation==horizontal; `rectangular` requires `tank_width`+`tank_length`+`tank_height`; `horizontal_elliptical_ends` requires `dish_depth`; `custom_strapping` requires `strapping_table_id`.
- `TankCreate(TankBase)`: unchanged (inherits validator).
- `TankRead(TankBase)` keep; add line `fuel_type: "FuelTypeRead | None" = None` optional? Keep minimal: TankRead uses `from_attributes`; the new columns map directly. Leave as-is (fields now include `fuel_type_id`, `tank_shape`, etc.).
- `TelemetryPoint`: add `gov_volume: float | None = None`, `net_volume: float | None = None`, `density_at_temperature: float | None = None`.

- [ ] **Step 4: Run to verify they pass + backend smoke**

Run: `cd /home/ubuntu/fuel_monitoring/platform && python3 -m pytest fmp/tests/unit/test_schemas.py -q`
Then: `python3 -c "import fmp.api.main; print('ok')"`
Expected: PASS and "ok"

- [ ] **Step 5: Commit**

```bash
git add platform/fmp/schemas/fuel.py platform/fmp/schemas/strapping.py platform/fmp/schemas/tanks.py platform/fmp/tests/unit/test_schemas.py
git commit -m "feat: fuel/strapping schemas + shape-aware tank DTOs"
```

---

### Task 6: Pipeline GOV/NSV persistence + live payload

**Files:**
- Modify: `platform/fmp/ingestion/pipeline.py`
- Modify: `platform/fmp/ingestion/batch_writer.py`
- Test: `platform/fmp/tests/unit/test_pipeline_events.py` (append behavior), `platform/fmp/tests/integration/test_telemetry_pipeline.py`

- [ ] **Step 1: Write failing pipeline test**

Append to `platform/fmp/tests/unit/test_pipeline_events.py` (read the file first to match its helpers/FakeRedis usage; it drives `IngestionPipeline.process` with a stubbed `tank`). Add:

```python
class _TankStub:
    id = uuid.uuid4()
    atmospheric_pressure = 0.0
    elevation = None
    calibration_factor = 1.0
    tank_orientation = "vertical"
    tank_shape = "vertical_cylinder"
    tank_diameter = 1.5
    tank_height = 2.0
    tank_length = None
    tank_width = None
    dish_depth = None
    low_level_threshold = None
    critical_level_threshold = None
    high_level_threshold = None
    low_volume_threshold = None
    high_volume_threshold = None
    fuel_type = type("FT", (), {"code": "diesel", "base_density": 845.0,
                                "thermal_expansion_coeff": 0.0008})()


async def test_processed_reading_carries_gov_nsv_density(tmp_session, fake_redis):
    pipeline = IngestionPipeline(write_batch=False)
    read = await pipeline.process(
        tmp_session, fake_redis, _TankStub(),
        pressure=0.082376, temperature=35.0,
    )
    assert read is not None
    assert read.gov_volume > 0
    expected_vcf = 1 - 0.0008 * (35 - 15)
    assert read.net_volume == pytest.approx(read.gov_volume * expected_vcf, rel=1e-6)
    assert read.density_at_temperature == pytest.approx(845.0 * (1 - 0.0008 * (35 - 15)))
    # live payload includes new fields
    msgs = fake_redis.published
    assert any("gov_volume" in json.dumps(m) for _, m in msgs)
```

(`tmp_session` — reuse the session helper the existing `test_pipeline_events.py` uses; check that file for the actual fixture/import names and mirror exactly.)

- [ ] **Step 2: Run to verify it fails**

Run: `cd /home/ubuntu/fuel_monitoring/platform && python3 -m pytest fmp/tests/unit/test_pipeline_events.py -q`
Expected: FAIL (test fails because `Read.gov_volume` missing or payload lacks field)

- [ ] **Step 3: Implement**

Update `ProcessedReading` dataclass in `pipeline.py`:

```python
@dataclass(frozen=True)
class ProcessedReading:
    tank_id: uuid.UUID
    timestamp: str
    pressure: float
    temperature: float
    level: float
    volume: float
    gov_volume: float
    net_volume: float
    density_at_temperature: float
    fill_percent: float
    is_outlier: bool
    alarms: tuple = ()
```

Update `IngestionPipeline.process` density/volume section:

```python
        if getattr(tank, "fuel_type", None) is not None:
            base_density = tank.fuel_type.base_density
            expansion_coeff = tank.fuel_type.thermal_expansion_coeff
        else:
            base_density = 750.0
            expansion_coeff = 0.00095
            logger.warning("tank %s has no fuel_type; using gasoline defaults", tank.id)
        density = density_at_temperature(base_density, expansion_coeff, temperature)

        level = pressure_to_level(
            pressure_bar=pressure,
            atmospheric_bar=tank.atmospheric_pressure or 0.0,
            density=density,
            elevation=tank.elevation,
            calibration_factor=tank.calibration_factor,
        )
        is_outlier = state.anomaly.update(level)
        level = state.pressure_ema.update(level)

        vcf = volume_correction_factor(expansion_coeff, temperature)
        gov = calculate_volume(
            level=level,
            orientation=tank.tank_orientation,
            tank_diameter=tank.tank_diameter,
            tank_length=tank.tank_length,
            tank_height=tank.tank_height,
            tank_shape=getattr(tank, "tank_shape", None),
            tank_width=getattr(tank, "tank_width", None),
            dish_depth=getattr(tank, "dish_depth", None),
        )
        nsv = gov * vcf
        percent = fill_percent(gov, tank.total_capacity_liters)
```

Update the persisted `read` dict to add `"gov_volume": gov, "net_volume": nsv, "density_at_temperature": density`, and `ProcessedReading(...)` return to pass the three new fields (order matches dataclass). Update `ProcessedReading` construction in `publish_live` first — payload:

```python
    await redis.publish(LIVE_CHANNEL, {
        "tank_id": str(reading.tank_id),
        "timestamp": reading.timestamp,
        "pressure": reading.pressure,
        "temperature": reading.temperature,
        "level": reading.level,
        "volume": reading.volume,
        "gov_volume": reading.gov_volume,
        "net_volume": reading.net_volume,
        "density_at_temperature": reading.density_at_temperature,
        "fill_percent": reading.fill_percent,
        "is_outlier": reading.is_outlier,
        "alarms": [...],
    })
```

Update `processor` imports in `process`: replace `temperature_compensated_density` with `density_at_temperature`, `volume_correction_factor`:

```python
        from fmp.ingestion.processor import (
            calculate_volume,
            density_at_temperature,
            fill_percent,
            pressure_to_level,
            volume_correction_factor,
        )
```

- [ ] **Step 4: Update `insert_measurements`**

In `platform/fmp/ingestion/batch_writer.py`, add columns to the insert statement for `gov_volume`, `net_volume`, `density_at_temperature` (they arrive in the `read` dict keys). Inspect `insert_measurements` first and mirror the existing column list.

- [ ] **Step 5: Run unit + integration telemetry tests**

Run: `cd /home/ubuntu/fuel_monitoring/platform && python3 -m pytest fmp/tests/unit/test_pipeline_events.py fmp/tests/unit/test_telemetry* -q`
(If `test_telemetry_pipeline.py` is in integration dir, run:)
`POSTGRES_PORT=5434 POSTGRES_DB=fuel_test POSTGRES_USER=fuelplatform POSTGRES_PASSWORD=fuelplatform123 REDIS_PORT=6479 python3 -m pytest fmp/tests/integration/test_telemetry_pipeline.py -q`
Expected: PASS. Update any existing assertions in `test_telemetry_pipeline.py`/`test_api_surface.py` that compare full `ProcessedReading`/payload equality (they now include the new fields).

- [ ] **Step 6: Commit**

```bash
git add platform/fmp/ingestion/pipeline.py platform/fmp/ingestion/batch_writer.py platform/fmp/tests/unit/test_pipeline_events.py platform/fmp/tests/integration/test_telemetry_pipeline.py
git commit -m "feat: pipeline computes GOV/NSV + density from tank fuel; live payload extended"
```

---

### Task 7: Alembic scaffold + migration 0001 + fuel seed

**Files:**
- Create: `platform/alembic.ini`, `platform/alembic/env.py`, `platform/alembic/script.py.mako`, `platform/alembic/versions/0001_fuel_dynamics.py`
- Create: `platform/fmp/scripts/seed_fuel_types.py`
- Modify: `platform/fmp/scripts/init_db.py`

- [ ] **Step 1: Scaffold Alembic (verify against real DB)**

Manual/CLI steps (no test — infra setup):

```bash
cd /home/ubuntu/fuel_monitoring/platform
POSTGRES_PORT=5434 POSTGRES_DB=fuel_test POSTGRES_USER=fuelplatform POSTGRES_PASSWORD=fuelplatform123 python3 -c "from fmp.core.database import config; u=config.database_url; print(u[:u.rfind('/')] + '/fuel_monitoring')"
# capture the admin URL (fuel_test is a copy; migrate fuel_monitoring, then re-copy to fuel_test for tests)
```

Wire `alembic/env.py` to read the URL from `fmp.core.config.get_settings()` (match `database.py` async URL building) and set `target_metadata = Base.metadata` (import `fmp.models`). Use async template; migration runs with `asyncio.run(migrate())`.

- [ ] **Step 2: Write migration `0001_fuel_dynamics.py`**

Contents:
1. `op.create_table("fuel_types", ...)` (uuid pk, code unique, name, base_density, thermal_expansion_coeff, max_vapor_pressure, viscosity_cst, created_at, updated_at).
2. `op.create_table("strapping_tables", ...)` (uuid pk, tank_id unique FK, calibration_data JSONB default `'[]'`, interpolation_method, timestamps).
3. `op.add_column("tanks", sa.Column("tank_shape", sa.String(20), server_default="vertical_cylinder"))`, plus `dish_depth` (Float, nullable), `tank_width` (Float, nullable), `fuel_type_id` (UUID, nullable, FK), `strapping_table_id` (UUID, nullable, FK).
4. Seed rows first in Python (invoke `fmp.scripts.seed_fuel_types.sync_seed(bind)`), then backfill: for each tank, pick the fuel_type whose `base_density` range contains the tank's `fluid_density` (gasoline ≤775, diesel ≤860, else ethanol) and set `fuel_type_id`.
5. `op.drop_column("tanks", "fluid_density")`.
6. `op.add_column("measurements", ...)` for `gov_volume`, `net_volume`, `density_at_temperature` (Float, nullable).
7. Downgrade: reverse (re-add fluid_density, drop new columns/tables).

- [ ] **Step 3: Write seed module `fmp/scripts/seed_fuel_types.py`**

```python
"""Idempotent seed of built-in fuel types."""
from __future__ import annotations

import asyncio

from sqlalchemy import text

DEFAULT_FUELS = [
    {"code": "gasoline", "name": "Gasoline", "base_density": 750.0,
     "thermal_expansion_coeff": 0.00095, "max_vapor_pressure": 60.0, "viscosity_cst": 0.6},
    {"code": "diesel", "name": "Diesel", "base_density": 845.0,
     "thermal_expansion_coeff": 0.00080, "max_vapor_pressure": 2.0, "viscosity_cst": 2.5},
    {"code": "kerosene", "name": "Kerosene", "base_density": 800.0,
     "thermal_expansion_coeff": 0.00090, "max_vapor_pressure": 1.5, "viscosity_cst": 1.4},
    {"code": "jet_fuel", "name": "Jet Fuel", "base_density": 810.0,
     "thermal_expansion_coeff": 0.00085, "max_vapor_pressure": 1.2, "viscosity_cst": 1.1},
    {"code": "ethanol", "name": "Ethanol", "base_density": 789.0,
     "thermal_expansion_coeff": 0.00110, "max_vapor_pressure": 16.0, "viscosity_cst": 1.2},
]

UPSERT_SQL = text(
    """INSERT INTO fuel_types (id, code, name, base_density, thermal_expansion_coeff,
                              max_vapor_pressure, viscosity_cst, created_at, updated_at)
       VALUES (gen_random_uuid(), :code, :name, :base_density, :thermal_expansion_coeff,
               :max_vapor_pressure, :viscosity_cst, now(), now())
       ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name,
                                        base_density = EXCLUDED.base_density,
                                        thermal_expansion_coeff = EXCLUDED.thermal_expansion_coeff,
                                        max_vapor_pressure = EXCLUDED.max_vapor_pressure,
                                        viscosity_cst = EXCLUDED.viscosity_cst"""
)


async def seed_fuel_types() -> int:
    from fmp.core.database import engine

    n = 0
    async with engine.begin() as conn:
        for fuel in DEFAULT_FUELS:
            await conn.execute(UPSERT_SQL, fuel)
            n += 1
    await engine.dispose()
    return n


if __name__ == "__main__":
    print(f"seeded {asyncio.run(seed_fuel_types())} fuel types")
```

- [ ] **Step 4: Hook seed into `init_db.py`**

In `platform/fmp/scripts/init_db.py`, after `create_all` and before `ensure_hypertables`, call `await seed_fuel_types()` (import the async function; note it disposes the engine, so call it last and keep `ensure_hypertables` before it; or refactor `seed_fuel_types` to accept a session/engine to avoid double-dispose).

- [ ] **Step 5: Verify migration against a scratch DB**

Run: `POSTGRES_PORT=5434 POSTGRES_DB=fuel_test POSTGRES_USER=fuelplatform POSTGRES_PASSWORD=fuelplatform123 python3 -m alembic upgrade head`
and re-run the full test suite (DB schema must still satisfy `create_all`/hypertable bootstrap in tests):

```bash
cd /home/ubuntu/fuel_monitoring/platform
POSTGRES_PORT=5434 POSTGRES_DB=fuel_test POSTGRES_USER=fuelplatform POSTGRES_PASSWORD=fuelplatform123 REDIS_PORT=6479 python3 -m pytest fmp/tests -q
```
Expected: all green. Then run `seed_fuel_types` standalone sanity:
`POSTGRES_PORT=5434 POSTGRES_DB=fuel_test POSTGRES_USER=fuelplatform POSTGRES_PASSWORD=fuelplatform123 python3 -m fmp.scripts.seed_fuel_types` → "seeded 5 fuel types".

- [ ] **Step 6: Commit**

```bash
git add platform/alembic.ini platform/alembic/ platform/fmp/scripts/seed_fuel_types.py platform/fmp/scripts/init_db.py
git commit -m "feat: alembic migration 0001 (fuel/strapping/measurement columns) + idempotent fuel seed"
```

---

### Task 8: Fuel-types + strapping routers, tank DTO wiring

**Files:**
- Create: `platform/fmp/api/v1/fuel_types.py`
- Create: `platform/fmp/api/v1/strapping.py`
- Modify: `platform/fmp/api/v1/tanks.py`, `platform/fmp/api/main.py`
- Test: `platform/fmp/tests/integration/test_fuel_dynamics_api.py`

- [ ] **Step 1: Write failing integration tests**

Create `platform/fmp/tests/integration/test_fuel_dynamics_api.py` (mirror `test_api_surface.py`'s `db` + override fixtures from `tests/integration/conftest.py`; a `token_override` fixture seeding an admin and overriding `get_current_user`):

```python
async def test_fuel_types_list_and_create_roles(db, token_override, client):
    # any authenticated (here admin override) may list
    r = await client.get("/api/v1/fuel-types")
    assert r.status_code == 200
    # bad payload rejected
    r = await client.post("/api/v1/fuel-types", json={"code": "bad density!"})
    assert r.status_code == 422
    # admin can create
    r = await client.post("/api/v1/fuel-types", json={
        "code": "test_fuel", "name": "Test", "base_density": 700.0,
        "thermal_expansion_coeff": 0.0009, "max_vapor_pressure": 3.0, "viscosity_cst": 1.0,
    })
    assert r.status_code == 201, r.text
    assert r.json()["base_density"] == 700.0


async def test_strapping_upsert_and_read(db, token_override, client, tank_seed):
    r = await client.put(f"/api/v1/tanks/{tank_seed.id}/strapping", json={
        "calibration_data": [{"height": 0.0, "volume": 0.0},
                             {"height": 1.0, "volume": 700.0},
                             {"height": 2.0, "volume": 1500.0}],
        "interpolation_method": "cubic_spline",
    })
    assert r.status_code == 200, r.text
    assert r.json()["interpolation_method"] == "cubic_spline"
    got = await client.get(f"/api/v1/tanks/{tank_seed.id}/strapping")
    assert got.status_code == 200 and len(got.json()["calibration_data"]) == 3
    # tank now points at the table
    tank = await client.get(f"/api/v1/tanks/{tank_seed.id}")
    assert tank.json()["strapping_table_id"] == r.json()["id"]


async def test_strapping_missing_returns_404(db, token_override, client, tank_seed):
    r = await client.get(f"/api/v1/tanks/{tank_seed.id}/strapping")
    assert r.status_code == 404
```

`token_override`: seed `User(role="admin")`, override `get_current_user`. `tank_seed`: create Company→Site→Tank (with a `fuel_type_id` from a seeded or created fuel). `client`: httpx `AsyncClient(ASGITransport(app))`.

- [ ] **Step 2: Run to verify failure**

Run:
```bash
cd /home/ubuntu/fuel_monitoring/platform
POSTGRES_PORT=5434 POSTGRES_DB=fuel_test POSTGRES_USER=fuelplatform POSTGRES_PASSWORD=fuelplatform123 REDIS_PORT=6479 python3 -m pytest fmp/tests/integration/test_fuel_dynamics_api.py -q
```
Expected: FAIL with 404 (routes absent).

- [ ] **Step 3: Implement fuel_types router**

`platform/fmp/api/v1/fuel_types.py`:

```python
"""Fuel type API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from fmp.api.deps import CurrentUser, PrivilegedUser, SessionDep
from fmp.models import FuelType
from fmp.schemas.fuel import FuelTypeCreate, FuelTypeRead

router = APIRouter(prefix="/api/v1/fuel-types", tags=["fuel-types"])


@router.get("", response_model=list[FuelTypeRead])
async def list_fuel_types(_: CurrentUser, session: SessionDep):
    rows = (await session.execute(
        select(FuelType).order_by(FuelType.code)
    )).scalars().all()
    return rows


@router.post("", response_model=FuelTypeRead, status_code=201)
async def create_fuel_type(payload: FuelTypeCreate, _: PrivilegedUser, session: SessionDep):
    dup = (await session.execute(
        select(FuelType).where(FuelType.code == payload.code)
    )).scalar_one_or_none()
    if dup is not None:
        raise HTTPException(409, "fuel type code already exists")
    fuel = FuelType(**payload.model_dump())
    session.add(fuel)
    await session.commit()
    await session.refresh(fuel)
    return fuel
```

- [ ] **Step 4: Implement strapping router**

`platform/fmp/api/v1/strapping.py`:

```python
"""Per-tank strapping (calibration) table API."""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from fmp.api.deps import CurrentUser, PrivilegedUser, SessionDep
from fmp.models import StrappingTable, Tank
from fmp.schemas.strapping import StrappingTableRead, StrappingTableUpsert

router = APIRouter(prefix="/api/v1/tanks/{tank_id}/strapping", tags=["strapping"])


def _to_read(row: StrappingTable) -> StrappingTableRead:
    data = row.calibration_data or []
    return StrappingTableRead(
        id=row.id, tank_id=row.tank_id,
        calibration_data=[{"height": p["height"], "volume": p["volume"]} for p in data],
        interpolation_method=row.interpolation_method,
        created_at=row.created_at,
    )


async def _require_tank(tank_id, session) -> Tank:
    tank = (await session.execute(
        select(Tank).where(Tank.id == tank_id, Tank.deleted_at.is_(None))
    )).scalar_one_or_none()
    if tank is None:
        raise HTTPException(404, "tank not found")
    return tank


@router.get("", response_model=StrappingTableRead)
async def get_strapping(tank_id: uuid.UUID, _: CurrentUser, session: SessionDep):
    await _require_tank(tank_id, session)
    row = (await session.execute(
        select(StrappingTable).where(StrappingTable.tank_id == tank_id)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "no strapping table for this tank")
    return _to_read(row)


@router.put("", response_model=StrappingTableRead)
async def upsert_strapping(
    tank_id: uuid.UUID, payload: StrappingTableUpsert, _: PrivilegedUser, session: SessionDep
):
    tank = await _require_tank(tank_id, session)
    row = (await session.execute(
        select(StrappingTable).where(StrappingTable.tank_id == tank_id)
    )).scalar_one_or_none()
    if row is None:
        row = StrappingTable(
            tank_id=tank_id,
            calibration_data=[p.model_dump() for p in payload.calibration_data],
            interpolation_method=payload.interpolation_method,
        )
        session.add(row)
    else:
        row.calibration_data = [p.model_dump() for p in payload.calibration_data]
        row.interpolation_method = payload.interpolation_method
    await session.flush()
    tank.strapping_table_id = row.id
    await session.commit()
    await session.refresh(row)
    return _to_read(row)
```

- [ ] **Step 5: Wire routers into `platform/fmp/api/main.py`**

Add `fuel_types` and `strapping` to the imports and `app.include_router(...)` calls. Also fix `platform/fmp/api/v1/tanks.py`: `create_tank`/`update` DTOs now carry `fuel_type_id`/`strapping_table_id`/`tank_shape` automatically via `TankCreate`/`TankRead`; ensure no code passes `fluid_density`.

- [ ] **Step 6: Run to verify pass**

Run:
```bash
cd /home/ubuntu/fuel_monitoring/platform
POSTGRES_PORT=5434 POSTGRES_DB=fuel_test POSTGRES_USER=fuelplatform POSTGRES_PASSWORD=fuelplatform123 REDIS_PORT=6479 python3 -m pytest fmp/tests/integration/test_fuel_dynamics_api.py fmp/tests/integration/test_api_surface.py -q
```
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add platform/fmp/api/v1/fuel_types.py platform/fmp/api/v1/strapping.py platform/fmp/api/v1/tanks.py platform/fmp/api/main.py platform/fmp/tests/integration/test_fuel_dynamics_api.py
git commit -m "feat: fuel-types + strapping APIs; shape-aware tank DTO wiring"
```

---

### Task 9: Dispensing read endpoints (frontend data)

**Files:**
- Create: `platform/fmp/schemas/dispensing_read.py`
- Modify: `platform/fmp/api/v1/dispensing.py`, `platform/fmp/api/main.py` (if needed)
- Test: `platform/fmp/tests/integration/test_dispensing_read_api.py`

- [ ] **Step 1: Write the failing integration test**

Create `platform/fmp/tests/integration/test_dispensing_read_api.py` (uses `db` + admin `token_override`; seeds Company→Employee→Allocation + DispenseTransaction via ORM directly like `test_dispense_flow.py` does — read that file and reuse its seed helper):

```python
async def test_allocation_and_transaction_reads(db, token_override, client):
    r = await client.get("/api/v1/dispensing/allocations?limit=10")
    assert r.status_code == 200 and isinstance(r.json(), list)
    r = await client.get("/api/v1/dispensing/transactions?dispenser_id=00000000-0000-0000-0000-000000000000")
    assert r.status_code == 200 and isinstance(r.json(), list)
    r = await client.get("/api/v1/dispensing/transactions?limit=5")
    assert r.status_code == 200
```

- [ ] **Step 2: Run to verify failure**

Expected: FAIL with 404 (endpoints absent).

- [ ] **Step 3: Implement schemas `fmp/schemas/dispensing_read.py`**

```python
"""Read-only DTOs for the dispensing/totalizer dashboards."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from fmp.models import DispenseTransaction   # noqa: F401 (field names mirror ORM)


class AllocationRead(BaseModel):
    id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str
    invoice_number: str | None = None
    allocated_liters: float
    dispensed_liters: float
    remaining_liters: float
    status: str
    created_at: datetime


class TransactionRead(BaseModel):
    id: int
    station_id: uuid.UUID
    dispenser_id: uuid.UUID
    employee_id: uuid.UUID
    requested_liters: float
    actual_liters: float
    secret_totalizer_before: int
    secret_totalizer_after: int
    status: str
    created_at: datetime
```

- [ ] **Step 4: Implement read endpoints in `dispensing.py`**

Append (import `select`, `desc`, strings from datetime via `datetime`):

```python
@router.get("/allocations", response_model=list[AllocationRead])
async def list_allocations(_, max_rows: int = 100, session: ... = ...):
    stmt = (select(Allocation).order_by(desc(Allocation.created_at)).limit(min(max_rows, 500)))
    rows = (await session.execute(stmt)).scalars().all()
    return [
        AllocationRead(
            id=a.id, employee_id=a.employee_id,
            employee_name=a.employee.name if a.employee else "",
            invoice_number=a.invoice_number,
            allocated_liters=a.allocated_liters,
            dispensed_liters=a.dispensed_liters,
            remaining_liters=a.remaining_liters,
            status=a.status, created_at=a.created_at,
        )
        for a in rows
    ]


@router.get("/transactions", response_model=list[TransactionRead])
async def list_transactions(dispenser_id: uuid.UUID | None = None,
                            limit: int = 200, ...):
    stmt = select(DispenseTransaction).order_by(desc(DispenseTransaction.created_at)).limit(min(limit, 1000))
    if dispenser_id:
        stmt = stmt.where(DispenseTransaction.dispenser_id == dispenser_id)
    ...
```

Wire `CurrentUser`/`SessionDep` (reuse `fmp.api.deps`) — the existing endpoints in the file still use `Depends(get_session)`; this task only ADDS the read endpoints with the new deps to keep the change additive and not break the edge contract of validate/complete.

- [ ] **Step 5: Run tests to verify pass**

Run the new integration test + `test_api_surface.py`.
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add platform/fmp/schemas/dispensing_read.py platform/fmp/api/v1/dispensing.py platform/fmp/tests/integration/test_dispensing_read_api.py
git commit -m "feat: read-only dispensing allocations/transactions endpoints for dashboards"
```

---

### Task 10: Full-suite verification + docs

**Files:**
- Modify: `platform/docs/architecture/directory-structure.md`

- [ ] **Step 1: Full suite + compose config**

Run:
```bash
cd /home/ubuntu/fuel_monitoring/platform
POSTGRES_PORT=5434 POSTGRES_DB=fuel_test POSTGRES_USER=fuelplatform POSTGRES_PASSWORD=fuelplatform123 REDIS_PORT=6479 python3 -m pytest fmp/tests -q
cd /home/ubuntu/fuel_monitoring && docker compose config --quiet
python3 -m compileall -q platform/fmp
```
Expected: all tests pass AND `docker compose config --quiet` is silent.

- [ ] **Step 2: Update `directory-structure.md`**

Add entries: `models/fuel.py`, `schemas/{fuel,strapping,dispensing_read}.py`, `api/v1/{fuel_types,strapping}.py`, `ingestion/tank_geometry.py`, `alembic/`, `scripts/seed_fuel_types.py`, new test files.

- [ ] **Step 3: Commit**

```bash
git add platform/docs/architecture/directory-structure.md
git commit -m "docs: fuel dynamics backend structure"
git push
```

---

## Self-Review Notes

- Spec §2 (models), §3 (engine), §4 (pipeline), §5 (API), §6 (migration/seed), §8 (tests) → Tasks 1-10 map 1:1.
- GOV/NSV persisted (spec §2.4) → Tasks 2, 3, 6.
- Fuel replaces fluid_density (spec §2.3) → Task 4, 5, 7.
- Custom strapping spline (spec §3.3) → Task 1, 3.
- Frontend-read endpoints (dispensing/allocations/transactions) are additions covered by Task 9 (needed by the frontend plan).
- Legacy heuristic-density tests removed deliberately (spec §8).