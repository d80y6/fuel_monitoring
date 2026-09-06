"""
Measurement Processor

This module provides the MeasurementProcessor class for processing tank measurements.
"""
import logging
import math
from datetime import datetime
from threading import Lock

logger = logging.getLogger(__name__)


class MeasurementProcessor:
    """Process raw sensor measurements into meaningful tank data."""

    def __init__(self, tank_config):
        self.tank_config = tank_config
        self.pressure_readings = []
        self.max_pressure_readings = 5
        self._last_level = None
        self._last_volume = None
        self._lock = Lock()

    def smooth_pressure(self, pressure):
        """Apply moving average smoothing to pressure readings (thread-safe)."""
        with self._lock:
            self.pressure_readings.append(pressure)

            if len(self.pressure_readings) > self.max_pressure_readings:
                self.pressure_readings.pop(0)

            if len(self.pressure_readings) >= 3:
                sorted_readings = sorted(self.pressure_readings)
                median_idx = len(sorted_readings) // 2

                valid_readings = []
                median = sorted_readings[median_idx]
                max_deviation = 0.002

                for reading in self.pressure_readings:
                    if abs(reading - median) / median <= max_deviation:
                        valid_readings.append(reading)

                if valid_readings:
                    return sum(valid_readings) / len(valid_readings)

            return pressure

    def process_measurement(self, pressure, temperature, status):
        """Process a raw measurement into tank data."""
        with self._lock:
            if pressure < 0:
                pressure = 0.0

            level = self.pressure_to_level(pressure, temperature)

            if self._last_level is not None:
                level = self._apply_hysteresis(level, self._last_level, self.tank_config.level_hysteresis)

            self._last_level = level

            volume = self.calculate_volume_from_level(level, temperature)

            fill_percent = self._calculate_fill_percent(volume)

            measurement_data = {
                'timestamp': datetime.utcnow(),
                'pressure': pressure,
                'temperature': temperature,
                'level': level,
                'volume': volume,
                'fill_percent': fill_percent,
                'status': status
            }

            return measurement_data

    def pressure_to_level(self, pressure, temperature=None):
        """Convert pressure to fluid level with temperature and elevation compensation."""
        pressure_pa = (pressure - self.tank_config.atmospheric_pressure) * 100000

        density = self._calculate_temperature_compensated_density(self.tank_config.fluid_density, temperature)
        gravity = self._calculate_elevation_compensated_gravity(self.tank_config.elevation)

        level = pressure_pa / (density * gravity)
        level = level * self.tank_config.calibration_factor

        return round(level, 3)

    def calculate_volume_from_level(self, level, temperature=None):
        """Calculate volume from level based on tank orientation with temperature compensation."""
        level = max(0, min(level, self.tank_config.tank_diameter if self.tank_config.tank_orientation == 'horizontal' else self.tank_config.tank_height))

        if self.tank_config.tank_orientation == 'horizontal':
            raw_volume = self._horizontal_tank_level_to_volume(level)
        else:
            volume_m3 = math.pi * (self.tank_config.tank_diameter / 2) ** 2 * level
            raw_volume = volume_m3 * 1000

        if temperature is not None:
            reference_temp = 15.0

            if abs(temperature - reference_temp) > 2.0:
                base_density = self.tank_config.fluid_density

                if 720 <= base_density <= 780:
                    volume_expansion = 0.00110
                elif 820 <= base_density <= 860:
                    volume_expansion = 0.00080
                else:
                    volume_expansion = 0.00095

                compensated_volume = raw_volume / (1 + volume_expansion * (temperature - reference_temp))

                logger.debug(f"Volume temperature compensation: Raw volume={raw_volume:.1f}L, "
                            f"Temp={temperature:.1f}C, Compensated volume={compensated_volume:.1f}L")

                return round(compensated_volume, 1)

        return round(raw_volume, 1)

    def _horizontal_tank_level_to_volume(self, level):
        """Calculate volume for a horizontal cylindrical tank based on liquid level."""
        level = max(0, min(level, self.tank_config.tank_diameter))

        radius = self.tank_config.tank_diameter / 2

        if level <= 0.001:
            return 0.0

        if level >= self.tank_config.tank_diameter - 0.001:
            return math.pi * radius ** 2 * self.tank_config.tank_height * 1000

        if level <= radius:
            theta = 2 * math.acos((radius - level) / radius)
            area = (radius ** 2 * (theta - math.sin(theta))) / 2
        else:
            h_empty = self.tank_config.tank_diameter - level
            theta = 2 * math.acos((radius - h_empty) / radius)
            empty_area = (radius ** 2 * (theta - math.sin(theta))) / 2
            area = math.pi * radius ** 2 - empty_area

        volume_m3 = area * self.tank_config.tank_height
        return volume_m3 * 1000

    def _calculate_fill_percent(self, volume):
        """Calculate fill percentage based on volume."""
        total_volume = self.tank_config.tank_volume * 1000

        if total_volume > 0:
            fill_percent = (volume / total_volume) * 100
        else:
            fill_percent = 0

        fill_percent = min(100, max(0, fill_percent))
        return round(fill_percent, 1)

    def _apply_hysteresis(self, current_value, last_value, hysteresis):
        """Apply hysteresis to a value to prevent fluctuations."""
        if abs(current_value - last_value) < hysteresis:
            return last_value
        return current_value

    def _calculate_temperature_compensated_density(self, base_density, temperature):
        """Calculate temperature-compensated fluid density."""
        if temperature is None:
            return base_density

        reference_temp = 15.0

        if 720 <= base_density <= 780:
            thermal_expansion = 0.00110
            fuel_type = "gasoline"
        elif 820 <= base_density <= 860:
            thermal_expansion = 0.00080
            fuel_type = "diesel"
        elif 700 <= base_density <= 820:
            thermal_expansion = 0.00095
            fuel_type = "other_petroleum"
        else:
            thermal_expansion = 0.00095
            fuel_type = "unknown"

        if fuel_type == "gasoline":
            damping_factor = 0.6
        elif fuel_type == "diesel":
            damping_factor = 0.4
        else:
            damping_factor = 0.5

        effective_temp_diff = (temperature - reference_temp) * damping_factor
        compensated_density = base_density / (1 + thermal_expansion * effective_temp_diff)

        logger.debug(f"Temperature compensation for {fuel_type}: Base density={base_density}, "
                    f"Temp={temperature}C, Compensated density={compensated_density}")

        return compensated_density

    def _calculate_elevation_compensated_gravity(self, elevation):
        """Calculate gravity compensated for elevation."""
        if elevation is None:
            return 9.80665

        standard_gravity = 9.80665
        gravity_gradient = 3.086e-6

        compensated_gravity = standard_gravity - (gravity_gradient * elevation)

        logger.debug(f"Elevation compensation: Elevation={elevation}m, Compensated gravity={compensated_gravity}")

        return compensated_gravity

    def get_stable_volume(self, volume, last_volume=None, hysteresis=None):
        """Apply enhanced hysteresis to volume to ensure stability."""
        if last_volume is None:
            return volume

        if hysteresis is None:
            hysteresis = max(1.0, self.tank_config.tank_volume * 0.001)

        if abs(volume - last_volume) < hysteresis:
            return last_volume

        return volume
