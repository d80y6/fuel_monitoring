"""
Measurement Processor

This module provides the MeasurementProcessor class for processing tank measurements.
"""
import logging
import math
from datetime import datetime

logger = logging.getLogger(__name__)

class MeasurementProcessor:
    """Process raw sensor measurements into meaningful tank data."""
    
    def __init__(self, tank_config):
        """
        Initialize the measurement processor.
        
        Args:
            tank_config: Tank configuration object
        """
        self.tank_config = tank_config
        self.pressure_readings = []
        self.max_pressure_readings = 5
    
    def smooth_pressure(self, pressure):
        """Apply moving average smoothing to pressure readings."""
        # Add current reading to history
        self.pressure_readings.append(pressure)
        
        # Keep only the most recent readings
        if len(self.pressure_readings) > self.max_pressure_readings:
            self.pressure_readings.pop(0)
        
        # Calculate average (exclude outliers if we have enough readings)
        if len(self.pressure_readings) >= 3:
            # Sort readings to find median
            sorted_readings = sorted(self.pressure_readings)
            median_idx = len(sorted_readings) // 2
        
            # Use readings close to median (exclude extreme outliers)
            valid_readings = []
            median = sorted_readings[median_idx]
            max_deviation = 0.002  # 0.1% deviation
        
            for reading in self.pressure_readings:
                if abs(reading - median) / median <= max_deviation:
                    valid_readings.append(reading)
        
            # If we have valid readings, use their average
            if valid_readings:
                return sum(valid_readings) / len(valid_readings)
        
        # If we don't have enough readings or valid readings, use the current value
        return pressure
    
    def process_measurement(self, pressure, temperature, status):
        """
        Process a raw measurement into tank data.
        
        Args:
            pressure: Pressure reading in bar
            temperature: Temperature reading in °C (or None)
            status: Status code from sensor
            
        Returns:
            dict: Processed measurement data
        """
        # Convert pressure to level
        level = self.pressure_to_level(pressure, temperature)
        
        # Apply hysteresis to level if we have a previous reading
        if hasattr(self, 'last_level') and self.last_level is not None:
            level = self._apply_hysteresis(level, self.last_level, self.tank_config.level_hysteresis)
        
        self.last_level = level
        
        # Calculate volume from level with temperature compensation
        volume = self.calculate_volume_from_level(level, temperature)
        
        # Calculate fill percentage
        fill_percent = self._calculate_fill_percent(volume)
        
        # Create measurement data dictionary
        measurement_data = {
            'timestamp': datetime.now(),
            'pressure': pressure,
            'temperature': temperature,
            'level': level,
            'volume': volume,
            'fill_percent': fill_percent,
            'status': status
        }
        
        return measurement_data
    
    def pressure_to_level(self, pressure, temperature=None):
        """
        Convert pressure to fluid level with temperature and elevation compensation.
        
        Args:
            pressure: Pressure in bar
            temperature: Current temperature in °C (optional)
            
        Returns:
            float: Fluid level in meters
        """
        # Convert pressure from bar to Pa (1 bar = 100,000 Pa)
        pressure_pa = (pressure - self.tank_config.atmospheric_pressure) * 100000
        
        # Get temperature-compensated density
        density = self._calculate_temperature_compensated_density(self.tank_config.fluid_density, temperature)
        
        # Get elevation-compensated gravity
        gravity = self._calculate_elevation_compensated_gravity(self.tank_config.elevation)
        
        # Calculate height using hydrostatic pressure formula: P = ρgh
        # h = P / (ρg)
        level = pressure_pa / (density * gravity)
        #level += 0.016  # Adjust for sensor offset (if applicable)
        
        # Apply calibration factor
        level = level * self.tank_config.calibration_factor
        
        return round(level, 3)
    
    def calculate_volume_from_level(self, level, temperature=None):
        """
        Calculate volume from level based on tank orientation with temperature compensation.
        
        Args:
            level: Fluid level in meters
            temperature: Current temperature in °C (optional)
            
        Returns:
            float: Volume in liters
        """
        # Ensure level is within bounds
        level = max(0, min(level, self.tank_config.tank_diameter if self.tank_config.tank_orientation == 'horizontal' else self.tank_config.tank_height))
        
        # Calculate raw volume based on tank orientation
        if self.tank_config.tank_orientation == 'horizontal':
            raw_volume = self._horizontal_tank_level_to_volume(level)
        else:
            # Calculate volume for cylindrical vertical tank
            volume_m3 = math.pi * (self.tank_config.tank_diameter/2)**2 * level
            raw_volume = volume_m3 * 1000  # Convert to liters
        
        # Apply temperature compensation to volume if temperature is available
        if temperature is not None:
            # Reference temperature (15°C is standard for petroleum products)
            reference_temp = 15.0
            
            # Skip compensation if temperature is close to reference
            if abs(temperature - reference_temp) > 2.0:
                # Determine fuel type based on density range
                base_density = self.tank_config.fluid_density
                
                if 720 <= base_density <= 780:
                    # Gasoline range
                    volume_expansion = 0.00110  # per °C
                elif 820 <= base_density <= 860:
                    # Diesel range
                    volume_expansion = 0.00080  # per °C
                else:
                    # Default value
                    volume_expansion = 0.00095  # per °C
                
                # Calculate temperature-compensated volume
                # V_15 = V_T / (1 + β(T - 15))
                compensated_volume = raw_volume / (1 + volume_expansion * (temperature - reference_temp))
                
                logger.debug(f"Volume temperature compensation: Raw volume={raw_volume:.1f}L, "
                            f"Temp={temperature:.1f}°C, Compensated volume={compensated_volume:.1f}L")
                
                return round(compensated_volume, 1)
        
        return round(raw_volume, 1)
    
    def _horizontal_tank_level_to_volume(self, level):
        """
        Calculate volume for a horizontal cylindrical tank based on liquid level.
        
        Args:
            level: Liquid level height from bottom of tank (m)
            
        Returns:
            float: Volume in liters
        """
        # Ensure level is within bounds
        level = max(0, min(level, self.tank_config.tank_diameter))
        
        # Calculate radius
        radius = self.tank_config.tank_diameter / 2
        
        # Handle edge cases
        if level <= 0.001:  # Nearly empty
            return 0.0
        
        if level >= self.tank_config.tank_diameter - 0.001:  # Nearly full
            return math.pi * radius**2 * self.tank_config.tank_height * 1000
        
        # Calculate the filled segment area
        if level <= radius:
            # Less than half full - calculate the filled segment
            theta = 2 * math.acos((radius - level) / radius)
            area = (radius**2 * (theta - math.sin(theta))) / 2
        else:
            # More than half full - calculate the filled segment
            # This is the full circle minus the empty segment
            h_empty = self.tank_config.tank_diameter - level  # height of empty segment
            theta = 2 * math.acos((radius - h_empty) / radius)
            empty_area = (radius**2 * (theta - math.sin(theta))) / 2
            area = math.pi * radius**2 - empty_area
        
        # Calculate volume in cubic meters
        volume_m3 = area * self.tank_config.tank_height
        
        # Convert to liters (1 m³ = 1000 liters)
        return volume_m3 * 1000
    
    def _calculate_fill_percent(self, volume):
        """
        Calculate fill percentage based on volume.
        
        Args:
            volume: Volume in liters
            
        Returns:
            float: Fill percentage (0-100)
        """
        # Calculate total tank volume in liters
        total_volume = self.tank_config.tank_volume * 1000
        
        # Calculate fill percentage
        if total_volume > 0:
            fill_percent = (volume / total_volume) * 100
        else:
            fill_percent = 0
        
        # Ensure percentage is between 0 and 100
        fill_percent = min(100, max(0, fill_percent))
        
        return round(fill_percent, 1)
    
    def _apply_hysteresis(self, current_value, last_value, hysteresis):
        """
        Apply hysteresis to a value to prevent fluctuations.
        
        Args:
            current_value: Current reading
            last_value: Previous reading
            hysteresis: Hysteresis threshold
            
        Returns:
            float: Value with hysteresis applied
        """
        # If the change is less than the hysteresis threshold, keep the old value
        if abs(current_value - last_value) < hysteresis:
            return last_value
        
        return current_value
    
    def _calculate_temperature_compensated_density(self, base_density, temperature):
        """
        Calculate temperature-compensated fluid density with improved fuel type detection.
        
        Args:
            base_density: Base density at reference temperature (kg/m³)
            temperature: Current temperature (°C)
            
        Returns:
            float: Compensated density (kg/m³)
        """
        if temperature is None:
            return base_density
            
        # Reference temperature (15°C is standard for petroleum products)
        reference_temp = 15.0
            
        # Determine fuel type based on density range
        if 720 <= base_density <= 780:
            # Gasoline range
            thermal_expansion = 0.00110  # per °C
            fuel_type = "gasoline"
        elif 820 <= base_density <= 860:
            # Diesel range
            thermal_expansion = 0.00080  # per °C
            fuel_type = "diesel"
        elif 700 <= base_density <= 820:
            # Other petroleum products (kerosene, jet fuel, etc.)
            thermal_expansion = 0.00095  # per °C
            fuel_type = "other_petroleum"
        else:
            # Unknown fluid
            thermal_expansion = 0.00095  # Default value
            fuel_type = "unknown"
            
        # Determine appropriate damping factor based on fuel type
        if fuel_type == "gasoline":
            # Gasoline is more sensitive to temperature
            damping_factor = 0.6  # Apply 60% of the temperature compensation
        elif fuel_type == "diesel":
            # Diesel is less sensitive to temperature
            damping_factor = 0.4  # Apply 40% of the temperature compensation
        else:
            # Default damping factor
            damping_factor = 0.5  # Apply 50% of the temperature compensation
            
        effective_temp_diff = (temperature - reference_temp) * damping_factor
            
        # Calculate temperature-compensated density
        # ρ = ρ₀ / (1 + β(T - T₀))
        compensated_density = base_density / (1 + thermal_expansion * effective_temp_diff)
            
        logger.debug(f"Temperature compensation for {fuel_type}: Base density={base_density}, "
                    f"Temp={temperature}°C, Compensated density={compensated_density}")
            
        return compensated_density
    
    def _calculate_elevation_compensated_gravity(self, elevation):
        """
        Calculate gravity compensated for elevation.
        
        Args:
            elevation: Elevation above sea level in meters
        
        Returns:
            float: Compensated gravity (m/s²)
        """
        if elevation is None:
            # Default to standard gravity if elevation is not provided
            return 9.80665
        
        # Calculate gravity at given elevation using the simplified formula:
        # g = g₀ - 3.086 × 10⁻⁶ × h
        # where:
        # g = gravity at elevation
        # g₀ = standard gravity at sea level (9.80665 m/s²)
        # h = elevation in meters
        standard_gravity = 9.80665  # m/s² at sea level
        gravity_gradient = 3.086e-6  # m/s²/m
        
        compensated_gravity = standard_gravity - (gravity_gradient * elevation)
        
        logger.debug(f"Elevation compensation: Elevation={elevation}m, Compensated gravity={compensated_gravity}")
        
        return compensated_gravity

    def get_stable_volume(self, volume, last_volume=None, hysteresis=None):
        """
        Apply enhanced hysteresis to volume to ensure stability.
        
        Args:
            volume: Current calculated volume
            last_volume: Previous volume (if available)
            hysteresis: Custom hysteresis value (or None to use config)
        
        Returns:
            float: Stabilized volume
        """
        if last_volume is None:
            return volume
        
        # Use provided hysteresis or get from config
        if hysteresis is None:
            # Use a larger hysteresis for volume (e.g., 0.1% of tank capacity)
            hysteresis = self.tank_config.tank_volume * 1000 * 0.001  # 0.1% of total volume
            hysteresis = max(1.0, hysteresis)  # At least 1 liter
        
        # Apply hysteresis
        if abs(volume - last_volume) < hysteresis:
            return last_volume
        
        return volume
