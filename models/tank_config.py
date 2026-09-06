"""
Tank Configuration

This module provides the TankConfig class for storing tank configuration.
"""
import json
import math
import logging

logger = logging.getLogger(__name__)


class TankConfig:
    """
    Tank configuration class.

    Stores configuration parameters for a tank.
    """

    def __init__(self):
        """Initialize the tank configuration."""
        # Tank parameters
        self.tank_orientation = 'vertical'
        self.tank_height = 2.0
        self.tank_diameter = 1.5
        self.fluid_density = 850
        self.atmospheric_pressure = 0.0
        self.elevation = 0.0
        self.tank_volume = 0.0

        # Connection settings
        self.host = None
        self.tcp_port = 2000
        self.device_address = 1

        # Sensor settings
        self.pressure_channel = 1
        self.temp_channel = 4
        self.calibration_factor = 1.0

        # Reconnection settings
        self.max_reconnect_attempts = 3
        self.reconnect_delay_base = 2

        # Measurement settings
        self.level_hysteresis = 0.001
        self.flow_threshold = 0.1
        self.pressure_smoothing = True

    @classmethod
    def from_database(cls, tank, app_config=None):
        """Create a TankConfig from a database Tank object."""
        config = cls()

        config.tank_orientation = tank.tank_orientation
        config.tank_height = tank.tank_height
        config.tank_diameter = tank.tank_diameter
        config.fluid_density = tank.fluid_density
        config.atmospheric_pressure = tank.atmospheric_pressure
        config.elevation = tank.elevation

        config.host = tank.host
        config.tcp_port = int(tank.tcp_port)
        config.device_address = int(tank.device_address)

        config.pressure_channel = tank.pressure_channel
        config.temp_channel = tank.temp_channel
        config.calibration_factor = tank.calibration_factor

        if hasattr(tank, 'level_hysteresis') and tank.level_hysteresis is not None:
            config.level_hysteresis = tank.level_hysteresis

        if hasattr(tank, 'flow_threshold') and tank.flow_threshold is not None:
            config.flow_threshold = tank.flow_threshold

        if hasattr(tank, 'pressure_smoothing'):
            config.pressure_smoothing = tank.pressure_smoothing

        # Calculate tank volume based on orientation
        config.tank_volume = cls._calculate_tank_volume(
            config.tank_orientation,
            config.tank_diameter,
            config.tank_height
        )

        if app_config:
            config.max_reconnect_attempts = app_config.get('MAX_RECONNECT_ATTEMPTS', 3)
            config.reconnect_delay_base = app_config.get('RECONNECT_DELAY_BASE', 2)

        logger.debug(f"Created tank config: {config.__dict__}")
        return config

    @staticmethod
    def _calculate_tank_volume(orientation, diameter, height):
        """Calculate tank volume in cubic meters based on orientation."""
        radius = diameter / 2.0
        if orientation == 'horizontal':
            # Horizontal cylinder: cross-section of circle * length
            return math.pi * radius ** 2 * height
        else:
            # Vertical cylinder: cross-section * height
            return math.pi * radius ** 2 * height

    def to_dict(self):
        """Serialize to a dictionary suitable for JSON/Redis storage."""
        return {
            'tank_orientation': self.tank_orientation,
            'tank_height': self.tank_height,
            'tank_diameter': self.tank_diameter,
            'fluid_density': self.fluid_density,
            'atmospheric_pressure': self.atmospheric_pressure,
            'elevation': self.elevation,
            'tank_volume': self.tank_volume,
            'host': self.host,
            'tcp_port': self.tcp_port,
            'device_address': self.device_address,
            'pressure_channel': self.pressure_channel,
            'temp_channel': self.temp_channel,
            'calibration_factor': self.calibration_factor,
            'max_reconnect_attempts': self.max_reconnect_attempts,
            'reconnect_delay_base': self.reconnect_delay_base,
            'level_hysteresis': self.level_hysteresis,
            'flow_threshold': self.flow_threshold,
            'pressure_smoothing': self.pressure_smoothing,
        }

    @classmethod
    def from_dict(cls, data):
        """Deserialize from a dictionary (e.g., loaded from Redis)."""
        if not data:
            return cls()

        config = cls()
        for key, value in data.items():
            if hasattr(config, key):
                setattr(config, key, value)
        return config

    def to_json(self):
        """Serialize to a JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str):
        """Deserialize from a JSON string."""
        if not json_str:
            return cls()
        data = json.loads(json_str)
        return cls.from_dict(data)

    def __str__(self):
        """Return string representation of the configuration."""
        return f"TankConfig(orientation={self.tank_orientation}, height={self.tank_height}m, diameter={self.tank_diameter}m)"
