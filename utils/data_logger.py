"""
Data Logger for Fuel Tank Measurements

This module provides a data logger for fuel tank measurements.
"""
import csv
import datetime
import os
import logging

logger = logging.getLogger("DataLogger")

class DataLogger:
    """
    Logger for fuel tank measurements
    
    Logs measurements to a CSV file for later analysis
    """
    def __init__(self, filename=None):
        """
        Initialize the data logger
        
        Args:
            filename: CSV file name or None to generate based on timestamp
        """
        if filename is None or not filename:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"fuel_tank_data_{timestamp}.csv"
        
        self.filename = filename
        self.file = None
        self.writer = None
        self.start_time = time.time()
        
        # Initialize the CSV file
        self._initialize_file()
    
    def _initialize_file(self):
        """Initialize the CSV file with headers"""
        try:
            # Create directory if it doesn't exist
            directory = os.path.dirname(self.filename)
            if directory and not os.path.exists(directory):
                os.makedirs(directory)
                
            self.file = open(self.filename, 'w', newline='')
            self.writer = csv.writer(self.file)
            
            # Write headers
            self.writer.writerow([
                "Timestamp", "Elapsed (s)", "Pressure (bar)", "Temperature (°C)",
                "Level (m)", "Volume (L)", "Flow Rate (L/min)", "Fill (%)"
            ])
            
            logger.info(f"Data logging initialized to {self.filename}")
        except Exception as e:
            logger.error(f"Failed to initialize data log file: {e}")
            if self.file:
                self.file.close()
                self.file = None
    
    def log_measurement(self, measurements):
        """
        Log a measurement to the CSV file
        
        Args:
            measurements: Dictionary with measurement values
        """
        if not self.writer or not measurements:
            return
        
        try:
            # Calculate elapsed time
            elapsed = time.time() - self.start_time
            
            # Get current timestamp
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Extract values with safe defaults
            pressure = measurements.get('pressure', float('nan'))
            temperature = measurements.get('temperature', float('nan'))
            level = measurements.get('level', float('nan'))
            volume = measurements.get('volume', float('nan'))
            flow_rate = measurements.get('flow_rate', float('nan'))
            fill_percent = measurements.get('fill_percent', float('nan'))
            
            # Write row
            self.writer.writerow([
                timestamp, f"{elapsed:.1f}", f"{pressure:.4f}", 
                f"{temperature:.2f}" if temperature is not None else "N/A",
                f"{level:.3f}", f"{volume:.1f}", f"{flow_rate:.2f}", f"{fill_percent:.1f}"
            ])
            
            # Flush to ensure data is written
            self.file.flush()
        except Exception as e:
            logger.error(f"Error logging measurement: {e}")
    
    def close(self):
        """Close the log file"""
        if self.file:
            self.file.close()
            self.file = None
            self.writer = None
            logger.info(f"Data logging to {self.filename} completed")
