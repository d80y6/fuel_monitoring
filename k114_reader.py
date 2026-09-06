#!/usr/bin/env python3
"""
K114 Reader - Communication interface for Keller K-114 converter
and connected pressure sensors

This module provides a Python interface for the Keller K-114 protocol
to read values from pressure transmitters connected via the K-114 converter.
"""
import serial
import struct
import time
import argparse
import math
import logging
import sys
import signal

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("K114Reader")


class K114Reader:
    """
    Client for communicating with Keller devices via K-114 converter

    Supports:
    - Reading pressure and temperature values
    - Reading device status and configuration
    - Reading K114 converter measurements
    """

    # Channel numbers for K114
    K114_U_IN = 1  # Voltage input
    K114_I_OUT = 2  # Current output
    K114_U_OUT = 3  # Voltage output (external device)
    K114_U_USB = 4  # USB voltage

    # Common channel numbers for connected devices
    CHANNEL_P1 = 1  # Pressure 1
    CHANNEL_P2 = 2  # Pressure 2 (if available)
    CHANNEL_T = 3  # Temperature (if available)
    CHANNEL_TOB1 = 4  # Temperature on board 1 (common)
    CHANNEL_TOB2 = 5  # Temperature on board 2 (if available)

    # Function codes
    INITIALIZE = 48
    READ_CHANNEL_FLOAT = 73
    READ_SERIAL_NUMBER = 69

    # Status codes
    STATUS_CODES = {
        0x01: "Pressure overrange",
        0x02: "Pressure underrange",
        0x04: "Temperature overrange",
        0x08: "Temperature underrange",
        0x10: "Hardware error",
        0x20: "Communication error",
        0x40: "Analog output error",
        0x80: "Not in standard mode",
    }

    def __init__(self, port, device_address=1, baudrate=9600, timeout=1.0):
        """
        Initialize the K114 reader

        Args:
            port: Serial port (e.g., COM1, /dev/ttyUSB0)
            device_address: Address of the connected device (default: 1)
            baudrate: Serial baudrate (default: 9600)
            timeout: Serial timeout in seconds (default: 1.0)
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.device_address = device_address
        self.k114_address = 253  # Fixed address for K114
        self.ser = None
        self.echo_on = True
        self.is_initialized = False
        self.device_info = None
        self.k114_info = None
        self.connection_type = "serial"  # Add this line

    def connect(self, max_retries=3):
        """
        Connect to the K114 converter with retries.

        Args:
            max_retries: Maximum number of connection attempts.

        Returns:
            True if connection successful, False otherwise
        """
        for attempt in range(max_retries):
            try:
                self.ser = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    bytesize=8,
                    parity=serial.PARITY_NONE,
                    stopbits=1,
                    timeout=self.timeout,
                )
                logger.info(f"Connected to {self.port} at {self.baudrate} baud")
                return True
            except Exception as e:
                logger.error(f"Connection attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(1)  # Wait before retrying
        logger.error(f"Failed to connect after {max_retries} attempts")
        return False

    def disconnect(self):
        """Disconnect from the device"""
        if self.ser and self.ser.is_open:
            self.ser.close()
            self.ser = None
            logger.info("Serial connection closed")

    def is_connected(self):
        """Check if connected to device"""
        return self.ser is not None and self.ser.is_open

    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.disconnect()

    def calculate_crc16(self, data):
        """
        Calculate CRC-16 for Keller bus protocol

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
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1
        return crc

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
                logger.error("Not connected")
                return None

            try:
                # Set timeout for this attempt
                self.ser.timeout = timeout
                logger.debug(f"Attempt {attempt + 1}: Sending request: {request.hex()}")

                # Send request
                self.ser.reset_input_buffer()
                self.ser.write(request)

                # If echo is on, read and discard the echo
                if self.echo_on:
                    echo = self.ser.read(len(request))
                    if len(echo) != len(request):
                        logger.error(
                            f"Echo error: expected {len(request)} bytes, got {len(echo)}"
                        )
                        continue  # Retry

                # Read first byte to determine response length
                first_byte = self.ser.read(1)
                if not first_byte:
                    logger.error("No response received")
                    continue  # Retry

                # Read function code
                function_byte = self.ser.read(1)
                if not function_byte:
                    logger.error("Incomplete response")
                    continue  # Retry

                # Determine expected response length based on function code
                function_code = function_byte[0]
                expected_length = self._get_expected_response_length(function_code)
                logger.debug(f"Function code: {function_code}, expected length: {expected_length}")

                # Read remaining bytes
                remaining = self.ser.read(expected_length - 2)

                # Combine all parts of the response
                response = first_byte + function_byte + remaining
                logger.debug(f"Received response: {response.hex()}")

                # Validate response CRC
                if not self._validate_response(response):
                    logger.error("Invalid CRC in response")
                    continue  # Retry

                return response
            except serial.SerialTimeoutException as e:
                logger.error(f"Timeout during attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(1)  # Wait before retrying
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(1)  # Wait before retrying

        logger.error(f"Failed after {max_retries} attempts")
        return None

    def _get_expected_response_length(self, function_code):
        """
        Determine expected response length based on Keller function code

        Args:
            function_code: Keller function code

        Returns:
            Expected response length in bytes
        """
        # Check if it's an exception response
        if function_code & 0x80:
            return 5  # 1(addr) + 1(func) + 1(exception) + 2(CRC) = 5 bytes

        # Map function codes to expected response lengths
        response_lengths = {
            # INITIALIZE: 1(addr) + 1(func) + 6(data) + 2(CRC) = 10 bytes
            48: 10,
            # READ_SERIAL_NUMBER: 1(addr) + 1(func) + 4(serial) + 2(CRC) = 8
            # bytes
            69: 8,
            # READ_CHANNEL_FLOAT: 1(addr) + 1(func) + 4(float) + 1(status) +
            # 2(CRC) = 9 bytes
            73: 9,
        }

        # Return expected length or a default value for unknown function codes
        # Default to 10 bytes for unknown functions
        return response_lengths.get(function_code, 10)

    def _validate_response(self, response):
        """
        Validate the response using CRC-16.

        Args:
            response: Response bytes

        Returns:
            True if CRC is valid, False otherwise
        """
        if len(response) < 2:
            return False

        crc_received = int.from_bytes(response[-2:], byteorder="little")
        crc_calculated = self.calculate_crc16(response[:-2])
        return crc_received == crc_calculated

    def initialize(self):
        """
        Initialize the device (Function 48)

        Returns:
            Device information dictionary or None if error
        """
        if not self.is_connected():
            logger.error("Not connected")
            return None

        # First initialize the K114 converter
        k114_info = self._initialize_device(self.k114_address)
        if not k114_info:
            logger.error("Failed to initialize K114 converter")
            return None

        self.k114_info = k114_info

        # Then initialize the connected device
        device_info = self._initialize_device(self.device_address)
        if not device_info:
            logger.error("Failed to initialize connected device")
            return None

        self.device_info = device_info
        self.is_initialized = True

        return device_info

    def _initialize_device(self, address):
        """
        Initialize a device at the specified address (Function 48)

        Args:
            address: Device address

        Returns:
            Device information dictionary or None if error
        """
        try:
            # Build request
            request = bytearray([address, self.INITIALIZE])

            # Calculate CRC
            crc = self.calculate_crc16(request)
            request.append((crc >> 8) & 0xFF)  # CRC high byte
            request.append(crc & 0xFF)  # CRC low byte

            # Send request and receive response
            response = self.send_receive(request)

            if not response or len(response) != 10:
                logger.error(
                    f"Invalid response length: {len(response) if response else 0}"
                )
                return None

            # Parse response
            if response[0] != address or response[1] != self.INITIALIZE:
                logger.error("Invalid response header")
                return None

            device_class = response[2]
            device_group = response[3]
            firmware_year = response[4]
            firmware_week = response[5]
            buffer_size = response[6]
            status = response[7]

            # Verify CRC
            received_crc = (response[8] << 8) | response[9]
            calculated_crc = self.calculate_crc16(response[:8])
            if received_crc != calculated_crc:
                logger.error("CRC check failed")
                return None

            device_info = {
                "class": device_class,
                "group": device_group,
                "firmware": f"{firmware_year}.{firmware_week}",
                "buffer_size": buffer_size,
                "status": status,
            }

            logger.info(
                f"Device initialized: Class {device_class}.{device_group}, Firmware {firmware_year}.{firmware_week}"
            )
            return device_info

        except Exception as e:
            logger.error(f"Error initializing device: {e}")
            return None

    def read_channel_float(self, channel, device_addr=None):
        """
        Read channel value as float (Function 73)

        Args:
            channel: Channel number
            device_addr: Device address (default: use self.device_address)

        Returns:
            Dictionary with value and status or None if error
        """
        if device_addr is None:
            device_addr = self.device_address

        if not self.is_connected():
            logger.error("Not connected")
            return None

        if not self.is_initialized and device_addr != self.k114_address:
            if not self.initialize():
                return None

        try:
            # Build request
            request = bytearray([device_addr, self.READ_CHANNEL_FLOAT, channel])

            # Calculate CRC
            crc = self.calculate_crc16(request)
            request.append((crc >> 8) & 0xFF)  # CRC high byte
            request.append(crc & 0xFF)  # CRC low byte

            # Send request and receive response
            response = self.send_receive(request)

            if not response or len(response) != 9:
                logger.error(
                    f"Invalid response length: {len(response) if response else 0}"
                )
                return None

            # Parse response
            if response[0] != device_addr or response[1] != self.READ_CHANNEL_FLOAT:
                logger.error("Invalid response header")
                return None

            value_bytes = response[2:6]
            status = response[6]

            # Verify CRC
            received_crc = (response[7] << 8) | response[8]
            calculated_crc = self.calculate_crc16(response[:7])
            if received_crc != calculated_crc:
                logger.error("CRC check failed")
                return None

            # Convert bytes to float
            value = struct.unpack(">f", bytes(value_bytes))[0]

            return {"value": value, "status": status}

        except Exception as e:
            logger.error(f"Error reading channel: {e}")
            return None

    def read_serial_number(self, device_addr=None):
        """
        Read device serial number (Function 69)

        Args:
            device_addr: Device address (default: use self.device_address)

        Returns:
            Serial number or None if error
        """
        if device_addr is None:
            device_addr = self.device_address

        if not self.is_connected():
            logger.error("Not connected")
            return None

        try:
            # Build request
            request = bytearray([device_addr, self.READ_SERIAL_NUMBER])

            # Calculate CRC
            crc = self.calculate_crc16(request)
            request.append((crc >> 8) & 0xFF)  # CRC high byte
            request.append(crc & 0xFF)  # CRC low byte

            # Send request and receive response
            response = self.send_receive(request)

            if not response or len(response) != 8:
                logger.error(
                    f"Invalid response length: {len(response) if response else 0}"
                )
                return None

            # Parse response
            if response[0] != device_addr or response[1] != self.READ_SERIAL_NUMBER:
                logger.error("Invalid response header")
                return None

            # Serial number is 4 bytes
            serial_number = (
                (response[2] << 24)
                | (response[3] << 16)
                | (response[4] << 8)
                | response[5]
            )

            # Verify CRC
            received_crc = (response[6] << 8) | response[7]
            calculated_crc = self.calculate_crc16(response[:6])
            if received_crc != calculated_crc:
                logger.error("CRC check failed")
                return None

            return serial_number

        except Exception as e:
            logger.error(f"Error reading serial number: {e}")
            return None

    def read_k114_measurements(self):
        """
        Read all available measurements from the K114 converter

        Returns:
            Dictionary with measurement values or None if error
        """
        results = {}

        # Channel 1: U-IN (Voltage input)
        u_in = self.read_channel_float(self.K114_U_IN, self.k114_address)
        if u_in:
            results["U-IN"] = u_in["value"]

        # Channel 2: I-OUT (Current supply)
        i_out = self.read_channel_float(self.K114_I_OUT, self.k114_address)
        if i_out:
            results["I-OUT"] = i_out["value"]

        # Channel 3: U-OUT (Voltage supply - external consumer)
        u_out = self.read_channel_float(self.K114_U_OUT, self.k114_address)
        if u_out:
            results["U-OUT"] = u_out["value"]

        # Channel 4: U-USB (USB voltage supply of K-114)
        u_usb = self.read_channel_float(self.K114_U_USB, self.k114_address)
        if u_usb:
            results["U-USB"] = u_usb["value"]

        return results

    def read_device_channels(self, num_channels=10, device_addr=None):
        """
        Try to read all available channels from the device

        Args:
            num_channels: Maximum number of channels to scan
            device_addr: Device address (default: use self.device_address)

        Returns:
            Dictionary with channel values
        """
        if device_addr is None:
            device_addr = self.device_address

        results = {}

        for ch in range(1, num_channels + 1):
            try:
                result = self.read_channel_float(ch, device_addr)
                if result and not math.isnan(
                    result["value"]
                ):  # Only include valid readings
                    results[ch] = result
            except Exception:
                # Skip channels that cause exceptions
                pass

        return results

    def read_pressure_and_temperature(self, pressure_ch=1, temp_ch=4, device_addr=None):
        """
        Read pressure and temperature from the specified channels

        Args:
            pressure_ch: Pressure channel number (default: 1)
            temp_ch: Temperature channel number (default: 4)
            device_addr: Device address (default: use self.device_address)

        Returns:
            Dictionary with pressure and temperature values
        """
        if device_addr is None:
            device_addr = self.device_address

        results = {}

        # Read pressure
        pressure = self.read_channel_float(pressure_ch, device_addr)
        if pressure:
            results["pressure"] = round(pressure,5)

        # Read temperature
        temperature = self.read_channel_float(temp_ch, device_addr)
        if temperature:
            results["temperature"] = round(temperature,1)

        return results

    def interpret_status(self, status):
        """
        Interpret status byte

        Args:
            status: Status byte

        Returns:
            Dictionary of status flags
        """
        result = {}
        for bit, description in self.STATUS_CODES.items():
            result[description] = bool(status & bit)

        return result


def main():
    """Main function for command-line interface"""
    parser = argparse.ArgumentParser(
        description="K114 Reader - Interface for Keller K-114 converter"
    )

    # Connection type
    connection_group = parser.add_argument_group("Connection")
    connection_type = connection_group.add_mutually_exclusive_group(required=True)
    connection_type.add_argument(
        "--serial",
        dest="connection_type",
        action="store_const",
        const="serial",
        help="Use serial connection",
    )
    connection_type.add_argument(
        "--tcp",
        dest="connection_type",
        action="store_const",
        const="tcp",
        help="Use TCP/IP connection",
    )

    # Serial connection options
    serial_group = parser.add_argument_group("Serial Connection")
    serial_group.add_argument("--port", help="Serial port (e.g., COM1, /dev/ttyUSB0)")
    serial_group.add_argument(
        "--baudrate",
        type=int,
        default=9600,
        choices=[9600, 115200],
        help="Baudrate (default: 9600)",
    )

    # TCP connection options
    tcp_group = parser.add_argument_group("TCP Connection")
    tcp_group.add_argument("--host", help="Hostname or IP address for TCP connection")
    tcp_group.add_argument(
        "--tcp-port", type=int, default=2000, help="TCP port number (default: 2000)"
    )

    # Device options
    parser.add_argument(
        "--address", type=int, default=1, help="Device address (default: 1)"
    )

    # Commands
    subparsers = parser.add_subparsers(dest="command", help="Command")

    # Initialize command
    subparsers.add_parser("init", help="Initialize device")

    # Read pressure command
    read_pressure_parser = subparsers.add_parser("read-pressure", help="Read pressure")
    read_pressure_parser.add_argument(
        "--channel",
        type=int,
        default=1,
        choices=[1, 2],
        help="Pressure channel (default: 1)",
    )

    # Read temperature command
    read_temp_parser = subparsers.add_parser(
        "read-temperature", help="Read temperature"
    )
    read_temp_parser.add_argument(
        "--channel",
        type=int,
        default=4,
        choices=[3, 4, 5],
        help="Temperature channel (3=T, 4=TOB1, 5=TOB2, default: 4)",
    )

    # Read serial number command
    subparsers.add_parser("read-serial", help="Read serial number")

    # Read K114 measurements command
    subparsers.add_parser("read-k114", help="Read K114 converter measurements")

    # Scan channels command
    scan_parser = subparsers.add_parser(
        "scan-channels", help="Scan all available channels"
    )
    scan_parser.add_argument(
        "--max-channels",
        type=int,
        default=10,
        help="Maximum number of channels to scan (default: 10)",
    )

    # Monitor command
    monitor_parser = subparsers.add_parser(
        "monitor", help="Monitor pressure and temperature"
    )
    monitor_parser.add_argument(
        "--pressure-ch", type=int, default=1, help="Pressure channel (default: 1)"
    )
    monitor_parser.add_argument(
        "--temp-ch", type=int, default=4, help="Temperature channel (default: 4)"
    )
    monitor_parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Update interval in seconds (default: 1.0)",
    )
    monitor_parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Monitoring duration in seconds (default: indefinite)",
    )

    args = parser.parse_args()

    # Validate connection arguments
    if args.connection_type == "serial" and not args.port:
        parser.error("--port is required for serial connection")
    elif args.connection_type == "tcp" and not args.host:
        parser.error("--host is required for TCP connection")

    # Register signal handler for Ctrl+C
    signal.signal(signal.SIGINT, lambda sig, frame: sys.exit(0))

    # Create appropriate client
    if args.connection_type == "tcp":
        client = K114TCPReader(args.host, args.tcp_port, args.address)
    else:
        client = K114Reader(args.port, args.address, args.baudrate)

    # Connect to device
    if not client.connect():
        sys.exit(1)
    try:
        # Process command
        if args.command == "init":
            device_info = client.initialize()
            if device_info:
                print("Device initialized successfully:")
                print(f"  Class: {device_info['class']}")
                print(f"  Group: {device_info['group']}")
                print(f"  Firmware: {device_info['firmware']}")
                print(f"  Buffer size: {device_info['buffer_size']}")
                print(f"  Status: {device_info['status']}")
            else:
                print("Failed to initialize device")
                sys.exit(1)

        elif args.command == "read-pressure":
            if not client.is_initialized:
                client.initialize()

            result = client.read_channel_float(args.channel)
            if result:
                print(f"Pressure (channel {args.channel}): {result['value']:.4f} bar")
                status_dict = client.interpret_status(result["status"])
                for key, value in status_dict.items():
                    if value:
                        print(f"  {key}")
            else:
                print("Failed to read pressure")
                sys.exit(1)

        elif args.command == "read-temperature":
            if not client.is_initialized:
                client.initialize()

            result = client.read_channel_float(args.channel)
            if result:
                print(f"Temperature (channel {args.channel}): {result['value']:.2f} °C")
                status_dict = client.interpret_status(result["status"])
                for key, value in status_dict.items():
                    if value:
                        print(f"  {key}")
            else:
                print("Failed to read temperature")
                sys.exit(1)

        elif args.command == "read-serial":
            if not client.is_initialized:
                client.initialize()

            serial_number = client.read_serial_number()
            if serial_number is not None:
                print(f"Serial number: {serial_number}")
            else:
                print("Failed to read serial number")
                sys.exit(1)

        elif args.command == "read-k114":
            # No need to initialize the device for K114 measurements
            measurements = client.read_k114_measurements()
            if measurements:
                print("K114 Measurements:")
                print(f"  U-IN: {measurements.get('U-IN', 'N/A'):.4f} V")
                print(f"  I-OUT: {measurements.get('I-OUT', 'N/A'):.4f} mA")
                print(f"  U-OUT: {measurements.get('U-OUT', 'N/A'):.4f} V")
                print(f"  U-USB: {measurements.get('U-USB', 'N/A'):.4f} V")
            else:
                print("Failed to read K114 measurements")
                sys.exit(1)

        elif args.command == "scan-channels":
            if not client.is_initialized:
                client.initialize()

            print("Scanning channels...")
            channels = client.read_device_channels(args.max_channels)
            if channels:
                print("Available channels:")
                for ch, data in channels.items():
                    print(
                        f"  Channel {ch}: {data['value']:.6f} (Status: {data['status']})"
                    )
            else:
                print("No valid channels found")
                sys.exit(1)

        elif args.command == "monitor":
            if not client.is_initialized:
                client.initialize()

            print("Monitoring pressure and temperature (Press Ctrl+C to stop)")
            print(
                "{:<10} {:<15} {:<15} {:<15}".format(
                    "Time (s)", "P1 (bar)", "TOB1 (°C)", "Status"
                )
            )
            print("-" * 60)

            start_time = time.time()
            try:
                while True:
                    # Read measurements
                    readings = client.read_pressure_and_temperature(
                        args.pressure_ch, args.temp_ch
                    )

                    # Calculate elapsed time
                    elapsed = time.time() - start_time

                    # Check if duration limit reached
                    if args.duration and elapsed > args.duration:
                        break

                    # Format values
                    if (
                        readings
                        and "pressure" in readings
                        and "temperature" in readings
                    ):
                        pressure = readings["pressure"]["value"]
                        temp = readings["temperature"]["value"]
                        status = readings["pressure"]["status"]

                        # Print values
                        print(
                            "{:<10.1f} {:<15.4f} {:<15.2f} {:<15}".format(
                                elapsed, pressure, temp, format(status, "08b")
                            )
                        )
                    else:
                        print("Error reading values")

                    # Wait for next update
                    time.sleep(args.interval)

            except KeyboardInterrupt:
                print("\nMonitoring stopped")

        else:
            print("No command specified. Use --help for available commands.")

    finally:
        # Disconnect from device
        client.disconnect()


if __name__ == "__main__":
    main()
