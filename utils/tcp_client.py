"""
K114 TCP Client

This module provides a TCP client for communicating with Keller devices via a TCP server.
"""
import socket
import struct
import time
import logging
import threading  # Add this import to fix the error

logger = logging.getLogger("K114TCPClient")

class K114TCPClient:
    """
    TCP client for communicating with Keller devices via a TCP server
    """
    # Exception error codes
    EXCEPTION_ILLEGAL_FUNCTION = 1
    EXCEPTION_ILLEGAL_DATA_ADDRESS = 2
    EXCEPTION_ILLEGAL_DATA_VALUE = 3
    EXCEPTION_SLAVE_DEVICE_FAILURE = 4
    EXCEPTION_INITIALIZATION = 32
    
    # Channel definitions
    CHANNEL_CH0 = 0  # Calculated channel
    CHANNEL_P1 = 1   # Pressure sensor 1
    CHANNEL_P2 = 2   # Pressure sensor 2
    CHANNEL_T = 3    # Temperature sensor
    CHANNEL_TOB1 = 4 # Temperature of pressure sensor 1
    CHANNEL_TOB2 = 5 # Temperature of pressure sensor 2
    
    # Modbus function codes
    MODBUS_READ_HOLDING_REGISTERS = 3
    MODBUS_WRITE_SINGLE_REGISTER = 6
    MODBUS_ECHO_TEST = 8
    MODBUS_WRITE_MULTIPLE_REGISTERS = 16
    
    # Keller bus function codes
    KELLER_READ_COEFFICIENTS = 30
    KELLER_WRITE_COEFFICIENTS = 31
    KELLER_READ_CONFIGURATION = 32
    KELLER_WRITE_CONFIGURATION = 33
    KELLER_INITIALIZE = 48
    KELLER_WRITE_READ_DEVICE_ADDRESS = 66
    KELLER_READ_SERIAL_NUMBER = 69
    KELLER_READ_FLOAT_VALUE = 73
    KELLER_READ_INTEGER_VALUE = 74
    KELLER_ZERO_COMMANDS = 95
    
    def __init__(self, host, port=2000, device_address=1, timeout=10.0, debug=False):
        """
        Initialize the K114 TCP client
        
        Args:
            host: Hostname or IP address
            port: TCP port (default: 2000)
            device_address: Address of the connected device (default: 1)
            timeout: Socket timeout in seconds (default: 10.0) - Increased timeout
            debug: Enable debug logging (default: False)
        """
        self.host = host
        self.port = port
        self.device_address = device_address
        self.timeout = timeout
        self.socket = None
        self.connected = False
        self.last_measurements = None
        self.debug = debug
        self.initialized = False
        self.lock = threading.Lock()  # Add lock for thread safety
        
        if self.debug:
            logger.setLevel(logging.DEBUG)
    
    def connect(self):
        """
        Connect to the TCP server
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Close existing connection if any
            if self.socket:
                self.disconnect()
            
            # Create new socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(self.timeout)
            self.socket.connect((self.host, self.port))
            
            # Add a small delay after connection
            time.sleep(0.5)
            
            self.connected = True
            logger.info(f"Connected to {self.host}:{self.port}")
            
            # Initialize the device
            if not self.initialize():
                logger.error("Failed to initialize device")
                self.disconnect()
                return False
                
            return True
        except Exception as e:
            logger.error(f"Failed to connect to {self.host}:{self.port}: {e}")
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
                self.socket = None
            self.connected = False
            return False
    
    def disconnect(self):
        """Disconnect from the TCP server"""
        with self.lock:  # Ensure thread safety
            if self.socket:
                try:
                    self.socket.close()
                    logger.info(f"Disconnected from {self.host}:{self.port}")
                except Exception as e:
                    logger.error(f"Error disconnecting from {self.host}:{self.port}: {e}")
                self.socket = None
            self.connected = False
            self.initialized = False
    
    def is_connected(self):
        """Check if connected to the TCP server"""
        return self.connected and self.socket is not None
    
    def send_receive(self, request):
        """
        Send request and receive response via TCP
        
        Args:
            request: Request bytes
            
        Returns:
            Response bytes or None if error
        """
        with self.lock:  # Ensure thread safety
            if not self.is_connected():
                logger.error("Not connected")
                return None
            
            try:
                # Send request
                logger.debug(f"Sending request: {request.hex()}")
                self.socket.sendall(request)
            
                # Receive response
                response = bytearray()
                start_time = time.time()
            
                while time.time() - start_time < self.timeout:
                    try:
                        chunk = self.socket.recv(1024)
                        if not chunk:
                            logger.error("Connection closed by remote host")
                            self.connected = False
                            return None
                    
                        response.extend(chunk)
                    
                        # Check if we have a complete response
                        if len(response) >= 7:  # Address, function, value (4 bytes), status
                            break
                    except socket.timeout:
                        logger.warning("Timeout waiting for response")
                        break
                
                if not response:
                    logger.error("No response received")
                    return None
            
                logger.debug(f"Received response: {response.hex()}")
                return bytes(response)
            
            except Exception as e:
                logger.error(f"Error in send_receive: {e}")
                self.connected = False
                return None
    
    def initialize(self):
        """
        Initialize the device with the proper initialization command
        
        Returns:
            True if successful, False otherwise
        """
        with self.lock:  # Ensure thread safety
            if not self.is_connected():
                logger.error("Cannot initialize: Not connected")
                return False
            
            try:
                # Send initialization command (function code 0x48)
                logger.info(f"Initializing device with address {self.device_address} using function code 0x48")
            
                # Create initialization request
                init_request = bytearray([
                    self.device_address,  # Device address
                    self.KELLER_INITIALIZE,  # Function code for initialization
                ])
            
                # Calculate CRC-16 (MODBUS)
                crc = self.calculate_crc16(init_request)
                init_request.extend([(crc >> 8) & 0xFF, crc & 0xFF])  # Add CRC
            
                # Send initialization request and receive response
                self.socket.sendall(init_request)
            
                # Receive response with a longer timeout
                response = bytearray()
                start_time = time.time()
            
                while time.time() - start_time < self.timeout:
                    try:
                        chunk = self.socket.recv(1024)
                        if not chunk:
                            logger.error("Connection closed during initialization")
                            self.connected = False
                            return False
                    
                        response.extend(chunk)
                    
                        # Check if we have a complete response
                        if len(response) >= 2:  # Address, function code
                            break
                    except socket.timeout:
                        logger.warning("Timeout waiting for initialization response")
                        break
            
                if not response:
                    logger.error("No response received to initialization command")
                    return False
            
                logger.debug(f"Initialization response: {response.hex()}")
            
                # Check if initialization was successful
                if len(response) >= 2 and response[0] == self.device_address and response[1] == self.KELLER_INITIALIZE:
                    logger.info("Device initialization successful")
                
                    # Wait a longer time for the device to complete initialization
                    time.sleep(3.0)
                    self.initialized = True
                    return True
                else:
                    logger.error(f"Invalid initialization response: {response.hex()}")
                    return False
                
            except Exception as e:
                logger.error(f"Error initializing device: {e}")
                self.connected = False
                return False
    
    def _echo_test(self):
        """
        Perform a simple echo test to verify communication
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Create echo test request (function code 0x08, subfunction 0x0000)
            echo_request = bytearray([
                self.device_address,  # Device address
                self.MODBUS_ECHO_TEST,  # Function code for echo test
                0x00, 0x00,  # Subfunction code (echo)
                0x12, 0x34   # Test data to echo back
            ])
        
            # Calculate CRC-16 (MODBUS)
            crc = self.calculate_crc16(echo_request)
            echo_request.extend([(crc >> 8) & 0xFF, crc & 0xFF])  # Add CRC
        
            # Send request and receive response
            echo_response = self.send_receive(echo_request)
        
            if not echo_response:
                logger.error("No response received to echo test")
                return False
        
            # Check if echo test was successful
            if (len(echo_response) >= 6 and 
                echo_response[0] == self.device_address and 
                echo_response[1] == self.MODBUS_ECHO_TEST and
                echo_response[2] == 0x00 and echo_response[3] == 0x00 and
                echo_response[4] == 0x12 and echo_response[5] == 0x34):
                return True
            else:
                logger.error(f"Invalid echo test response: {echo_response.hex()}")
                return False
            
        except Exception as e:
            logger.error(f"Error in echo test: {e}")
            return False
    
    def read_channel_float(self, channel):
        """
        Read a float value from a channel
        
        Args:
            channel: Channel number (1-7)
            
        Returns:
            Dictionary with value and status, or None if error
        """
        # Ensure we're connected and initialized
        if not self.is_connected() or not self.initialized:
            logger.info(f"Need to connect/initialize before reading channel {channel}")
            if not self.connect():  # This will also initialize
                return None
        
        try:
            # Create request
            request = bytearray([
                self.device_address,  # Device address
                self.KELLER_READ_FLOAT_VALUE,  # Function code (read float)
                channel               # Channel number
            ])
            
            # Calculate CRC-16 (MODBUS)
            crc = self.calculate_crc16(request)
            request.extend([(crc >> 8) & 0xFF, crc & 0xFF])  # Add CRC
            
            # Send request and receive response
            response = self.send_receive(request)
            if not response:
                return None
            
            # Check response
            if len(response) < 7:
                logger.error(f"Invalid response length: {len(response)}")
                return None
            
            if response[0] != self.device_address:
                logger.error(f"Invalid device address in response: expected {self.device_address}, got {response[0]}")
                return None
            
            if response[1] != self.KELLER_READ_FLOAT_VALUE:
                logger.error(f"Invalid function code in response: expected 0x{self.KELLER_READ_FLOAT_VALUE:02x}, got 0x{response[1]:02x}")
                return None
            
            # Extract value and status
            value_bytes = response[2:6]
            status = response[6]
            
            # Convert bytes to float (IEEE 754 format)
            try:
                value = struct.unpack('>f', value_bytes)[0]
                return {
                    'value': value,
                    'status': status
                }
            except struct.error as e:
                logger.error(f"Failed to unpack float value: {e}")
                return None
            
        except Exception as e:
            logger.error(f"Error reading channel {channel}: {e}")
            return None
    
    def calculate_crc16(self, data):
        """
        Calculate CRC-16 (MODBUS) for Keller protocol
        
        Args:
            data: Data bytes
            
        Returns:
            CRC-16 value
        """
        crc = 0xFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x0001:
                    crc = (crc >> 1) ^ 0xA001  # MODBUS polynomial
                else:
                    crc = crc >> 1
        return crc
    
    def interpret_status(self, status):
        """
        Interpret status byte
        
        Args:
            status: Status byte
            
        Returns:
            Dictionary with status flags
        """
        return {
            'Communication Error': bool(status & 0x01),
            'Memory Error': bool(status & 0x02),
            'Sensor Error': bool(status & 0x04),
            'Math Error': bool(status & 0x08),
            'New Min/Max': bool(status & 0x10),
            'Busy': bool(status & 0x20),
            'Negative': bool(status & 0x40),
            'Overflow': bool(status & 0x80)
        }
