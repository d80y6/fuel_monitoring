#!/usr/bin/env python3
"""
K114 Reader

This module provides the K114Reader base class for communicating with K114 converters.
"""
import logging
import struct
import time
from models.keller_protocol import KellerProtocol

logger = logging.getLogger(__name__)

class K114Reader:
    """
    Base class for K114 readers
    """
    
    def __init__(self, device_address=1):
        """
        Initialize the K114 reader
        
        Args:
            device_address: Device address (default: 1)
        """
        self.device_address = device_address
        logger.info(f"K114Reader initialized with device_address: {device_address}")
    
    def _send_request(self, request):
        """
        Send a request to the K114 converter and receive the response
        
        Args:
            request: Request bytes
            
        Returns:
            bytes: Response bytes or None if error
        """
        raise NotImplementedError("_send_request must be implemented by subclasses")
    
    def initialize(self, max_retries=3):
        """
        Initialize the K114 converter with retry logic
        
        Args:
            max_retries: Maximum number of retry attempts
        
        Returns:
            bool: True if successful, False otherwise
        """
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # Send initialization command
                # Function code 0x30 (48) - Initialize
                request = KellerProtocol.create_request(self.device_address, KellerProtocol.INITIALIZE)
                
                # Send request and get response
                response = self._send_request(request)
                
                # Check if response is valid (timeout check)
                if not response:
                    logger.error("Transmission error occurred during initialization")
                    retry_count += 1
                    continue
                
                # Check if this is an error response
                if response[1] & 0x80:
                    error_code = response[2] if len(response) >= 5 else 0
                    
                    # Exception 2: Incorrect length
                    if error_code == 0x02:
                        logger.error("Incorrect length, check your request")
                        retry_count += 1
                        continue
                    
                    # Other errors
                    else:
                        logger.error(f"Initialization error code: 0x{error_code:02x}")
                        retry_count += 1
                        continue
                
                # Check if response is correct
                if response[1] != KellerProtocol.INITIALIZE:
                    logger.error(f"Invalid response to initialization command: {' '.join(f'{b:02x}' for b in response)}")
                    retry_count += 1
                    continue
                
                logger.info("Successfully initialized K114 converter")
                return True
                
            except Exception as e:
                logger.error(f"Error initializing K114 converter: {str(e)}")
                retry_count += 1
        
        # If we've exhausted all retries
        logger.error(f"Failed to initialize K114 converter after {max_retries} attempts")
        return False
    
    def read_channel_float(self, channel, max_retries=3):
        """
        Read a float value from a channel with retry logic.
        
        Args:
            channel: Channel number (e.g., P1 or TOB1)
            max_retries: Maximum number of retry attempts
        
        Returns:
            dict: Dictionary with value and status, or None if error
        """
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # Function code 0x49 - Read Channel Float
                request = KellerProtocol.create_request(self.device_address, KellerProtocol.READ_CHANNEL_FLOAT, channel)
                
                # Send request and get response
                response = self._send_request(request)
                
                # Check if response is valid (timeout check is handled in _send_request)
                if not response:
                    logger.error("Transmission error occurred")
                    retry_count += 1
                    continue
                
                # Check if this is an error response (function code with high bit set)
                if response[1] & 0x80:
                    error_code = response[2] if len(response) >= 5 else 0
                    
                    # Exception 2 or 3: Invalid channel or message
                    if error_code in [0x02, 0x03]:
                        logger.error(f"Invalid Channel or message, check your request. Error code: 0x{error_code:02x}")
                        retry_count += 1
                        continue
                    
                    # Exception 32: Need to initialize
                    elif error_code == 0x20:  # 0x20 is 32 in decimal
                        logger.info("Device needs initialization")
                        
                        # Proceed to Initialize Function 48
                        init_success = self.initialize()
                        if not init_success:
                            logger.error("Initialization failed")
                            retry_count += 1
                            continue
                        else:
                            logger.info("Initialization successful, retrying read")
                            # Don't increment retry_count here as initialization was successful
                            continue
                    
                    # Other errors
                    else:
                        error_messages = {
                            0x01: "Illegal function",
                            0x04: "Device failure",
                            0x05: "Acknowledge",
                            0x06: "Device busy",
                            0x07: "Negative acknowledge",
                            0x08: "Memory parity error",
                            0x0A: "Gateway path unavailable",
                            0x0B: "Gateway target device failed to respond"
                        }
                        
                        error_message = error_messages.get(error_code, f"Unknown error code: 0x{error_code:02x}")
                        logger.error(f"Device error: {error_message}")
                        retry_count += 1
                        continue
                
                # Check if response has the correct function code
                if response[1] != KellerProtocol.READ_CHANNEL_FLOAT:
                    logger.error(f"Invalid response function code: {response[1]}")
                    retry_count += 1
                    continue
                
                # Check if response is long enough for a float value
                if len(response) < 9:
                    logger.error(f"Response too short for float value: {len(response)} bytes")
                    retry_count += 1
                    continue
                
                # Extract float value (4 bytes) and status (1 bytes)
                value_bytes = response[2:6]
                status_bytes = response[-3]
                
                # Convert bytes to float (big-endian)
                value = struct.unpack('>f', value_bytes)[0]
                status = status_bytes
                
                # Check status byte as per the flow
                # "If P1, TOB1, /Std: STAT & 0b10010010 == 0"
                if (status & 0b10010010) != 0:
                    logger.warning(f"Invalid value received. Status: 0x{status:04x}")
                    retry_count += 1
                    continue
                
                logger.debug(f"Read channel {channel}: value={value}, status={status}")
                
                return {
                    'value': value,
                    'status': status
                }
                
            except Exception as e:
                logger.error(f"Error reading channel {channel}: {str(e)}")
                retry_count += 1
        
        # If we've exhausted all retries
        logger.error(f"Failed to read channel {channel} after {max_retries} attempts")
        return None
    
    def _validate_response(self, response):
        """
        Validate a response packet.
        
        Args:
            response: Response bytes
            
        Returns:
            bool: True if valid, False otherwise
        """
        return KellerProtocol.verify_response(response)
    
    def _send_request(self, request):
        """
        Send a request to the K114 converter.
        
        This method should be implemented by subclasses.
        
        Args:
            request: Request bytes
            
        Returns:
            bytes: Response bytes or None if error
        """
        raise NotImplementedError("_send_request must be implemented by subclasses")
