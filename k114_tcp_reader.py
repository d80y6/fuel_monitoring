#!/usr/bin/env python3
"""
K114 TCP Reader - TCP/IP client for Keller K-114 protocol

This module provides a TCP/IP client implementation of the K114Reader interface
for communicating with Keller devices via a TCP server.
"""
import socket
import struct
import time
import logging
from k114_reader import K114Reader

logger = logging.getLogger("K114TCPReader")

# Constants
DEFAULT_TCP_PORT = 2000
DEFAULT_DEVICE_ADDRESS = 1
DEFAULT_TIMEOUT = 1.0
MAX_RETRIES = 3
BUFFER_SIZE = 1024

class K114TCPReader(K114Reader):
    """
    TCP/IP client for communicating with Keller devices via a TCP server
    
    Inherits from K114Reader to maintain the same interface but uses
    TCP/IP communication instead of serial.
    """
    
    def __init__(self, host, port=DEFAULT_TCP_PORT, device_address=DEFAULT_DEVICE_ADDRESS, timeout=DEFAULT_TIMEOUT):
        """
        Initialize the K114 TCP reader
        
        Args:
            host: Hostname or IP address
            port: TCP port (default: 2000)
            device_address: Address of the connected device (default: 1)
            timeout: Socket timeout in seconds (default: 1.0)
        """
        # Initialize parent class with dummy values
        super().__init__("TCP", device_address, 9600, timeout)
        
        # Override with TCP-specific values
        self.host = host
        self.port = port
        self.socket = None
        self.echo_on = False  # TCP doesn't have echo
        self.connection_attempts = 0
        self.max_connection_attempts = 5
    
    def connect(self):
        """
        Connect to the TCP server
        
        Returns:
            True if connection successful, False otherwise
        """
        # Check if we've exceeded max connection attempts
        if self.connection_attempts >= self.max_connection_attempts:
            logger.error(f"Exceeded maximum connection attempts ({self.max_connection_attempts})")
            return False
            
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(self.timeout)
            self.socket.connect((self.host, self.port))
            logger.info(f"Connected to {self.host}:{self.port}")
            self.connection_attempts = 0  # Reset counter on successful connection
            return True
        except Exception as e:
            self.connection_attempts += 1
            logger.error(f"Failed to connect to {self.host}:{self.port}: {e} (attempt {self.connection_attempts}/{self.max_connection_attempts})")
            self.socket = None
            return False
    
    def disconnect(self):
        """Disconnect from the TCP server"""
        if self.socket:
            try:
                self.socket.close()
                logger.info(f"Disconnected from {self.host}:{self.port}")
            except Exception as e:
                logger.error(f"Error disconnecting from {self.host}:{self.port}: {e}")
            self.socket = None
    
    def is_connected(self):
        """Check if connected to the TCP server"""
        return self.socket is not None
    
    def send_receive(self, request, max_retries=3, timeout=None):
        """
        Send request and receive response with retries and timeout.

        Args:
            request: Request bytes
            max_retries: Maximum number of retries
            timeout: Optional timeout in seconds

        Returns:
            Response bytes or None if error
        """
        timeout = timeout or self.timeout
        logger.debug(f"Starting send_receive with max_retries={max_retries}, timeout={timeout}")
        for attempt in range(max_retries):
            if not self.is_connected():
                logger.warning("Not connected, attempting to reconnect")
                if not self.connect():
                    logger.error("Reconnection failed")
                    return None

            try:
                # Set timeout for this attempt
                self.socket.settimeout(timeout)
                logger.debug(f"Attempt {attempt + 1}: Sending request: {request.hex()}")

                # Send request
                self.socket.sendall(request)

                # Receive response
                response = bytearray()
                start_time = time.time()

                while time.time() - start_time < timeout:
                    try:
                        chunk = self.socket.recv(BUFFER_SIZE)
                        if not chunk:
                            logger.error("Connection closed by server")
                            self.disconnect()
                            continue  # Retry

                        response.extend(chunk)
                        logger.debug(f"Received chunk: {chunk.hex()}")

                        # Check if we have a complete response
                        if len(response) >= 4:  # At least address, function, and CRC
                            if len(response) >= response[1] + 3:  # Address + Function + Data + CRC (2 bytes)
                                break
                    except socket.timeout:
                        continue
                    except socket.error as e:
                        logger.error(f"Socket error during receive: {e}")
                        self.disconnect()
                        continue  # Retry

                if not response:
                    logger.error("No response received")
                    continue  # Retry

                # Validate response CRC
                if not self._validate_response(response):
                    logger.error("Invalid CRC in response")
                    continue  # Retry

                logger.debug(f"Received response: {response.hex()}")
                return bytes(response)
            except socket.error as e:
                logger.error(f"Attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(1)  # Wait before retrying

        logger.error(f"Failed after {max_retries} attempts")
        return None
