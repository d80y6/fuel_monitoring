"""
Tank Configuration

This module provides the TankConfig class for storing tank configuration.
"""
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
        self.level_hysteresis = 0.001  # Default hysteresis in meters
        self.flow_threshold = 0.1      # Default flow threshold in L/min
        self.pressure_smoothing = True # Enable pressure smoothing
    
    @classmethod
    def from_database(cls, tank, app_config=None):
        """
        Create a TankConfig from a database Tank object.
        
        Args:
            tank: Tank database object
            app_config: Application configuration dictionary
            
        Returns:
            TankConfig: Configuration object
        """
        config = cls()
        
        # Tank parameters - using correct field names from database.py
        config.tank_orientation = tank.tank_orientation
        config.tank_height = tank.tank_height
        config.tank_diameter = tank.tank_diameter
        config.fluid_density = tank.fluid_density
        config.atmospheric_pressure = tank.atmospheric_pressure
        config.elevation = tank.elevation
        
        # Connection settings
        config.host = tank.host
        config.tcp_port = int(tank.tcp_port)  # Ensure tcp_port is an integer
        config.device_address = int(tank.device_address)  # Ensure device_address is an integer
        
        # Sensor settings
        config.pressure_channel = tank.pressure_channel
        config.temp_channel = tank.temp_channel
        config.calibration_factor = tank.calibration_factor
        
        # Custom settings if available
        if hasattr(tank, 'level_hysteresis') and tank.level_hysteresis is not None:
            config.level_hysteresis = tank.level_hysteresis
        
        if hasattr(tank, 'flow_threshold') and tank.flow_threshold is not None:
            config.flow_threshold = tank.flow_threshold
        
        if hasattr(tank, 'pressure_smoothing'):
            config.pressure_smoothing = tank.pressure_smoothing
        
        # Calculate tank volume
        if config.tank_orientation == 'vertical':
            config.tank_volume = 3.14159 * (config.tank_diameter / 2) ** 2 * config.tank_height
        else:
            # Horizontal cylinder volume
            config.tank_volume = 3.14159 * (config.tank_diameter / 2) ** 2 * config.tank_height
        
        # Add app config settings if provided
        if app_config:
            config.max_reconnect_attempts = app_config.get('MAX_RECONNECT_ATTEMPTS', 3)
            config.reconnect_delay_base = app_config.get('RECONNECT_DELAY_BASE', 2)
        
        logger.debug(f"Created tank config: {config.__dict__}")
        return config
    
    def __str__(self):
        """Return string representation of the configuration."""
        return f"TankConfig(orientation={self.tank_orientation}, height={self.tank_height}m, diameter={self.tank_diameter}m)"
