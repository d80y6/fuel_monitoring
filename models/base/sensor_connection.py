"""
Sensor Connection Interface

This module provides a common interface for different sensor connection types.
"""
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class SensorConnection(ABC):
    """Abstract base class for sensor connections."""
    
    @abstractmethod
    def connect(self):
        """
        Connect to the sensor.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        pass
    
    @abstractmethod
    def disconnect(self):
        """
        Disconnect from the sensor.
        
        Returns:
            bool: True if disconnection successful, False otherwise
        """
        pass
    
    @abstractmethod
    def is_connected(self):
        """
        Check if connected to the sensor.
        
        Returns:
            bool: True if connected, False otherwise
        """
        pass
    
    @abstractmethod
    def read_channel_float(self, channel):
        """
        Read a float value from the specified channel.
        
        Args:
            channel: Channel number to read from
            
        Returns:
            dict: Dictionary containing 'value' and 'status' keys or None if error
        """
        pass
    
    @abstractmethod
    def initialize(self):
        """
        Initialize the sensor connection.
        
        Returns:
            bool: True if initialization successful, False otherwise
        """
        pass