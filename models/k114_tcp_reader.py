#!/usr/bin/env python3
"""
K114 TCP Reader

This module provides the K114TCPReader class for communicating with K114 converters over TCP.
"""
import socket
import time
import logging
from models.k114_reader import K114Reader, KellerProtocol

logger = logging.getLogger(__name__)

class K114TCPReader(K114Reader):
    """
    K114 reader implementation for TCP/IP connections
    """
    
    def __init__(self, host, port, device_address=1, timeout=5.0):
        """
        Initialize the K114 TCP reader
        
        Args:
            host: Host/IP address
            port: TCP port
            device_address: Device address (default: 1)
            timeout: Timeout in seconds (default: 5.0)
        """
        super().__init__(device_address)
        self.host = host
        self.port = port
        self.timeout = timeout
        self.socket = None
        logger.info(f"K114TCPReader initialized with device_address: {device_address}")
    
    def connect(self):
        """
        Connect to the K114 converter via TCP
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logger.info(f"Connecting to {self.host}:{self.port}")
            
            # Create socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(self.timeout)
            
            # Connect to server
            self.socket.connect((self.host, self.port))
            
            # Initialize the device
            if not self.initialize():
                logger.error("Failed to initialize device")
                self.disconnect()
                return False
            
            return True
            
        except socket.error as e:
            logger.error(f"Socket error: {str(e)}")
            self.socket = None
            return False
        except Exception as e:
            logger.error(f"Error connecting to {self.host}:{self.port}: {str(e)}")
            self.socket = None
            return False
    
    def disconnect(self):
        """
        Disconnect from the K114 converter
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if self.socket:
                self.socket.close()
                self.socket = None
            
            logger.info(f"Disconnected from {self.host}:{self.port}")
            return True
            
        except Exception as e:
            logger.error(f"Error disconnecting from {self.host}:{self.port}: {str(e)}")
            self.socket = None
            return False
    
    def is_connected(self):
        """
        Check if connected to the K114 converter
        
        Returns:
            bool: True if connected, False otherwise
        """
        return self.socket is not None
    
    def _send_request(self, request):
        """
        Send a request to the K114 converter and receive the response
        
        Args:
            request: Request bytes
            
        Returns:
            bytes: Response bytes or None if error
        """
        try:
            if not self.socket:
                logger.error("Cannot send request: Not connected")
                return None
            
            # Log the request being sent
            logger.info(f"Sending request: {' '.join(f'{b:02x}' for b in request)}")
            
            # Send request
            self.socket.sendall(request)
            
            # Read response
            response = self._read_response()
            
            return response
            
        except socket.error as e:
            logger.error(f"Socket error: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error sending request: {str(e)}")
            return None
    
    def _read_response(self):
        """
        Read a response from the K114 converter
        
        Returns:
            bytes: Response bytes or None if error
        """
        try:
            if not self.socket:
                logger.error("Cannot read response: Not connected")
                return None
            
            # Read response with timeout
            response = bytearray()
            start_time = time.time()
            
            while time.time() - start_time < self.timeout:
                try:
                    chunk = self.socket.recv(1024)
                    if not chunk:
                        break
                    
                    response.extend(chunk)
                    
                    # Check if we have a complete response
                    if len(response) >= 3:  # At least address, function, and one data byte
                        function_code = response[1]
                        
                        # Determine expected length based on function code
                        if function_code == 0x30:  # INITIALIZE
                            expected_length = 10  # addr + func + 6 bytes + 2 CRC
                        elif function_code == 0x49:  # READ_CHANNEL_FLOAT
                            expected_length = 9   # addr + func + 4 bytes float + 2 status + 2 CRC
                        elif function_code == 0x5F:  # READ_SERIAL_NUMBER
                            expected_length = 8   # addr + func + 4 bytes serial + 2 CRC
                        else:
                            expected_length = 4   # addr + func + 2 CRC
                        
                        if len(response) >= expected_length:
                            break
                except socket.timeout:
                    continue
            
            if not response:
                logger.error("No response received")
                return None
            
            # Log the complete response
            logger.info(f"Received response: {' '.join(f'{b:02x}' for b in response)}")
            
            return bytes(response)
            
        except socket.timeout:
            logger.error("Timeout reading response")
            return None
        except socket.error as e:
            logger.error(f"Socket error: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error reading response: {str(e)}")
            return None
    
    def calculate_crc16(self, data):
        """
        Calculate CRC-16 for Keller bus protocol
        
        Args:
            data: Data bytes
            
        Returns:
            int: CRC-16 value
        """
        return KellerProtocol.calculate_crc16(data)
    
    def validate_response(self, response):
        """
        Validate a response from the K114 converter
        
        Args:
            response: Response bytes
            
        Returns:
            bool: True if valid, False otherwise
        """
        return KellerProtocol.verify_response(response)
