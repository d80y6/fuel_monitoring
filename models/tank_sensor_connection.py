"""
Tank Sensor Connection

This module provides the TankSensorConnection class for connecting to tank sensors.
"""
import logging
import time
import socket
import math
from models.k114_tcp_reader import K114TCPReader

logger = logging.getLogger(__name__)

class TankSensorConnection:
    """
    Tank Sensor Connection class.
    
    Handles connection to tank sensors via K114 converters.
    """
    
    def __init__(self, host, tcp_port, device_address, max_reconnect_attempts=3, reconnect_delay_base=2):
        """
        Initialize the tank sensor connection.
        
        Args:
            host: Host address of the K114 converter
            tcp_port: TCP port of the K114 converter
            device_address: Device address of the sensor
            max_reconnect_attempts: Maximum number of reconnection attempts
            reconnect_delay_base: Base delay for exponential backoff
        """
        self.host = host
        self.tcp_port = tcp_port
        self.device_address = device_address
        self.max_reconnect_attempts = max_reconnect_attempts
        self.reconnect_delay_base = reconnect_delay_base
        
        # Log the device address to verify it's correct
        logger.info(f"Initializing connection with device_address: {self.device_address}")
        
        self.client = None
        self.connected = False
        self.connect_attempts = 0
        self.last_connect_time = 0
    
    def connect(self):
        """
        Connect to the tank sensor.
        
        Returns:
            bool: True if successful, False otherwise
        """
        # Check if already connected
        if self.connected and self.client and self.client.is_connected():
            return True
        
        # Check if we've exceeded the maximum number of reconnection attempts
        if self.connect_attempts >= self.max_reconnect_attempts:
            # Calculate time since last attempt
            time_since_last = time.time() - self.last_connect_time
            
            # Calculate backoff time based on number of attempts
            backoff_time = self.reconnect_delay_base ** min(self.connect_attempts, 10)
            
            # If not enough time has passed, don't try again yet
            if time_since_last < backoff_time:
                logger.debug(f"Not attempting reconnection yet. Waiting {backoff_time - time_since_last:.1f}s more")
                return False
        
        # Update last connect time and increment attempts
        self.last_connect_time = time.time()
        self.connect_attempts += 1
        
        try:
            # Create client if it doesn't exist
            if self.client is None:
                # Explicitly log the device address being used
                logger.info(f"Creating K114TCPReader with device_address: {self.device_address}")
                
                self.client = K114TCPReader(
                    self.host,
                    self.tcp_port,
                    self.device_address,  # Make sure this is being passed correctly
                    timeout=5.0  # Increase timeout for more reliability
                )
            
            # Connect to device
            if not self.client.connect():
                logger.error(f"Failed to connect to device at {self.host}:{self.tcp_port} with address {self.device_address}")
                return False
            
            # Initialize device with retry logic
            init_attempts = 0
            max_init_attempts = 3
            
            while init_attempts < max_init_attempts:
                if self.client.initialize():
                    # Successfully initialized
                    self.connected = True
                    self.connect_attempts = 0  # Reset attempts counter on success
                    logger.info(f"Successfully connected to device at {self.host}:{self.tcp_port} with address {self.device_address}")
                    return True
                
                # Failed to initialize, try again
                init_attempts += 1
                if init_attempts < max_init_attempts:
                    logger.warning(f"Failed to initialize device, retrying ({init_attempts}/{max_init_attempts})")
                    time.sleep(1)  # Short delay between initialization attempts
            
            # If we get here, initialization failed
            logger.error(f"Failed to initialize device after {max_init_attempts} attempts")
            self.client.disconnect()
            self.connected = False
            return False
            
        except (ConnectionError, socket.error, TimeoutError) as e:
            logger.error(f"Connection error: {str(e)}")
            self.connected = False
            return False
        except Exception as e:
            logger.error(f"Unexpected error connecting to device: {str(e)}")
            self.connected = False
            return False
    
    def disconnect(self):
        """
        Disconnect from the tank sensor.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if self.client:
                self.client.disconnect()
            
            self.connected = False
            self.client = None
            return True
            
        except Exception as e:
            logger.error(f"Error disconnecting from device: {str(e)}")
            self.connected = False
            self.client = None
            return False
    
    def read_channel_float(self, channel):
        """
        Read a float value from a channel.
        
        Args:
            channel: Channel number
            
        Returns:
            dict: Dictionary with value and status, or None if error
        """
        try:
            if not self.connected:
                logger.warning("Cannot read channel: Not connected")
                return None
            
            # Read value from channel
            result = self.client.read_channel_float(channel)
            
            # Check if result is valid
            if result is None:
                logger.error(f"Failed to read channel {channel}")
                return None
            
            # Check if value is NaN
            if math.isnan(result['value']):
                logger.warning(f"Channel {channel} returned NaN")
                return None
            
            return result
            
        except Exception as e:
            logger.error(f"Error reading channel {channel}: {str(e)}")
            # Mark as disconnected on error
            self.connected = False
            return None
    
    def _reconnect(self):
        """
        Attempt to reconnect with exponential backoff.
        
        Returns:
            bool: True if successful, False otherwise
        """
        for attempt in range(1, self.max_reconnect_attempts + 1):
            logger.info(f"Reconnection attempt {attempt}/{self.max_reconnect_attempts}")
            
            # Calculate delay with exponential backoff
            delay = self.reconnect_delay_base ** attempt
            time.sleep(delay)
            
            # Try to connect
            if self.connect():
                logger.info(f"Reconnected on attempt {attempt}")
                return True
        
        logger.error(f"Failed to reconnect after {self.max_reconnect_attempts} attempts")
        return False
    
    def is_connected(self):
        """
        Check if connected to the sensor.
        
        Returns:
            bool: True if connected, False otherwise
        """
        return self.connected and self.client and self.client.is_connected()
