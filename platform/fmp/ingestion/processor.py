"""Telemetry ingestion processor: raw sensor readings -> calibrated tank data.

Pure, dependency-free math (physics + statistics) so the ingestion pipeline can
be unit-tested exhaustively and run on the edge as well as the server.

Reference physics ported from the legacy ``models/measurement_processor.py``;
adds EMA smoothing and MAD Z-score outlier rejection.
"""
from __future__ import annotations

import math

STANDARD_GRAVITY = 9.80665
GRAVITY_GRADIENT = 3.086e-6

THERMAL_EXPANSION = {
    "gasoline": (0.00110, 0.6),
    "diesel": (0.00080, 0.4),
    "other_petroleum": (0.00095, 0.5),
}


def _fuel_class(base_density: float) -> tuple[str, float, float]:
    if 720 <= base_density <= 780:
        return "gasoline", *THERMAL_EXPANSION["gasoline"]
    if 820 <= base_density <= 860:
        return "diesel", *THERMAL_EXPANSION["diesel"]
    return "other_petroleum", *THERMAL_EXPANSION["other_petroleum"]


def elevation_compensated_gravity(elevation: float | None) -> float:
    if elevation is None:
        return STANDARD_GRAVITY
    return STANDARD_GRAVITY - GRAVITY_GRADIENT * elevation


def fuel_expansion_coefficient(base_density: float) -> float:
    """Thermal expansion coefficient for a legacy fuel-density heuristic.

    Temporary bridge for the pipeline until real FuelType coefficients are
    wired in a later task; returns the expansion coefficient by fuel class.
    """
    return _fuel_class(base_density)[1]


def pressure_to_level(
    pressure_bar: float,
    atmospheric_bar: float,
    density: float,
    elevation: float | None,
    calibration_factor: float,
) -> float:
    """Convert gauge pressure to fluid level in meters (hydrostatics)."""
    pressure_pa = max(0.0, (pressure_bar - atmospheric_bar) * 100_000)
    gravity = elevation_compensated_gravity(elevation)
    level = pressure_pa / (density * gravity)
    return round(level * calibration_factor, 3)


def _horizontal_tank_level_to_volume(level: float, diameter: float, length: float) -> float:
    level = max(0.0, min(level, diameter))
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
        empty_area = (radius**2 * (theta - math.sin(theta))) / 2
        area = math.pi * radius**2 - empty_area

    return area * length * 1000


def calculate_volume(
    level: float,
    orientation: str,
    tank_diameter: float,
    tank_length: float | None,
    tank_height: float | None = None,
) -> float:
    """Volume in liters from a level reading, clamped to physical dimensions.

    ``orientation`` is ``"vertical"`` or ``"horizontal"``. For vertical tanks the
    usable height is ``tank_height``; for horizontal tanks ``tank_length`` is the
    cylinder length and ``tank_diameter`` the shell diameter.
    """
    if tank_diameter <= 0:
        return 0.0

    if orientation == "horizontal":
        max_level = tank_diameter
        length = tank_length or 0.0
        raw_volume = _horizontal_tank_level_to_volume(level, tank_diameter, length)
    else:
        max_level = tank_height or tank_diameter
        level = max(0.0, min(level, max_level))
        volume_m3 = math.pi * (tank_diameter / 2.0) ** 2 * level
        raw_volume = volume_m3 * 1000

    return round(raw_volume, 1)


def fill_percent(volume: float, total_capacity_liters: float) -> float:
    if total_capacity_liters <= 0:
        return 0.0
    percent = (volume / total_capacity_liters) * 100.0
    return round(min(100.0, max(0.0, percent)), 1)


class EMA:
    """Exponential moving average for pressure/level smoothing."""

    def __init__(self, span: int) -> None:
        self.alpha = 2.0 / (span + 1)
        self.value: float | None = None

    def update(self, sample: float) -> float:
        if self.value is None:
            self.value = sample
        else:
            self.value = self.alpha * sample + (1 - self.alpha) * self.value
        return self.value


class MADAnomalyDetector:
    """Rolling-window modified Z-score (median absolute deviation) outlier detector."""

    def __init__(self, window: int, threshold: float = 3.5) -> None:
        self.window = window
        self.threshold = threshold
        self._samples: list[float] = []

    def update(self, sample: float) -> bool:
        """Feed a sample; returns True when it is a statistical outlier."""
        self._samples.append(sample)
        if len(self._samples) > self.window:
            self._samples.pop(0)

        if len(self._samples) < self.window:
            return False

        sorted_samples = sorted(self._samples)
        median = sorted_samples[len(sorted_samples) // 2]
        deviations = sorted(abs(s - median) for s in self._samples)
        mad = deviations[len(deviations) // 2]

        if mad <= 1e-9:
            # all-but-current samples identical: any deviation is a spike
            return abs(sample - median) > 1e-6

        z_score = 0.6745 * (sample - median) / mad
        return abs(z_score) >= self.threshold


# Re-export the fuel-dynamics helpers (kept for backward-compatible imports).
from fmp.ingestion.tank_geometry import (  # noqa: F401
    density_at_temperature,
    interpolate_strapping,
    net_standard_volume,
    volume_correction_factor,
)