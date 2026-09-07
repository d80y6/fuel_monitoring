"""Telemetry ingestion processor: raw sensor readings -> calibrated tank data.

Pure, dependency-free math (physics + statistics) so the ingestion pipeline can
be unit-tested exhaustively and run on the edge as well as the server.

Reference physics ported from the legacy ``models/measurement_processor.py``;
adds EMA smoothing and MAD Z-score outlier rejection.
"""
from __future__ import annotations

STANDARD_GRAVITY = 9.80665
GRAVITY_GRADIENT = 3.086e-6


def elevation_compensated_gravity(elevation: float | None) -> float:
    if elevation is None:
        return STANDARD_GRAVITY
    return STANDARD_GRAVITY - GRAVITY_GRADIENT * elevation


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
    shape = tank_shape or ("vertical_cylinder" if orientation == "vertical" else "horizontal_cylinder")
    if tank_diameter <= 0 and shape not in ("custom_strapping", "rectangular"):
        return 0.0
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