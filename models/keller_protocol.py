"""
Keller Protocol

This module provides the KellerProtocol class for working with the Keller bus protocol.
"""
import logging

logger = logging.getLogger(__name__)

class KellerProtocol:
    """
    Keller Protocol class.
    
    Provides methods for working with the Keller bus protocol.
    """
    
    # Function codes
    INITIALIZE = 0x30
    READ_CHANNEL_FLOAT = 0x49
    READ_SERIAL_NUMBER = 0x5F
    
    @staticmethod
    def calculate_crc16(data):
        """
        Calculate CRC-16 for Keller bus protocol.
        
        Args:
            data: Data bytes
            
        Returns:
            int: CRC-16 value
        """
        crc = 0xFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x0001:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1
        return crc
    
    @staticmethod
    def create_request(address, function, data=None):
        """
        Create a request packet.
        
        Args:
            address: Device address
            function: Function code
            data: Optional data bytes
            
        Returns:
            bytes: Request packet
        """
        # Build request: address + function + data
        request = bytearray([address, function])
        
        if data is not None:
            if isinstance(data, int):
                request.append(data)
            elif isinstance(data, (bytes, bytearray)):
                request.extend(data)
        
        # Calculate CRC
        crc = KellerProtocol.calculate_crc16(request)
        
        # Add CRC to request with HIGH byte first, then low byte
        # This matches the working client's byte order
        request.append((crc >> 8) & 0xFF)  # High byte
        request.append(crc & 0xFF)  # Low byte
        
        return bytes(request)
    
    @staticmethod
    def verify_response(response):
        """
        Verify a response packet.
        
        Args:
            response: Response bytes
            
        Returns:
            bool: True if valid, False otherwise
        """
        if len(response) < 3:
            return False
        
        # Extract data and CRC
        data = response[:-2]
        
        # Try both byte orders for CRC
        received_crc_be = (response[-2] << 8) | response[-1]  # Big-endian (high byte first)
        received_crc_le = (response[-1] << 8) | response[-2]  # Little-endian (low byte first)
        
        # Calculate CRC
        calculated_crc = KellerProtocol.calculate_crc16(data)
        
        # Log details for debugging
        logger.debug(f"Response CRC check: data={data.hex(' ')}, received_be=0x{received_crc_be:04x}, received_le=0x{received_crc_le:04x}, calculated=0x{calculated_crc:04x}")
        
        # Check both byte orders
        if received_crc_be == calculated_crc:
            return True
        elif received_crc_le == calculated_crc:
            # If little-endian matches, log it for future reference
            logger.debug("CRC matched with little-endian byte order")
            return True
        else:
            logger.error(f"CRC check failed: data={data.hex(' ')}, received_be=0x{received_crc_be:04x}, received_le=0x{received_crc_le:04x}, calculated=0x{calculated_crc:04x}")
            return False
    
    @staticmethod
    def parse_serial_number(response):
        """
        Parse serial number from response.
        
        Args:
            response: Response bytes
            
        Returns:
            int: Serial number or None if error
        """
        if len(response) < 6:
            return None
        
        # Extract serial number (4 bytes)
        serial_number = (response[2] << 24) | (response[3] << 16) | (response[4] << 8) | response[5]
        
        return serial_number
    
    @staticmethod
    def parse_device_info(response):
        """
        Parse device info from response.
        
        Args:
            response: Response bytes
            
        Returns:
            dict: Device info or None if error
        """
        if len(response) < 8:
            return None
        
        # Extract device info
        device_class = response[2]
        device_group = response[3]
        firmware_year = response[4]
        firmware_week = response[5]
        buffer_size = response[6]
        device_status = response[7]
        
        return {
            'device_class': device_class,
            'device_group': device_group,
            'firmware_year': firmware_year,
            'firmware_week': firmware_week,
            'buffer_size': buffer_size,
            'device_status': device_status
        }
    
    @staticmethod
    def parse_float_response(response):
        """
        Parse float response.
        
        Args:
            response: Response bytes
            
        Returns:
            tuple: (value, status) or None if error
        """
        if len(response) < 8:
            return None
        
        # Extract value (4 bytes) and status (2 bytes)
        import struct
        value = struct.unpack('>f', response[2:6])[0]
        status = (response[6] << 8) | response[7]
        
        return (value, status)