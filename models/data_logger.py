#!/usr/bin/env python3
"""
Data Logger Module

Provides the DataLogger class for logging fuel tank measurements to a CSV file.
"""
import csv
import datetime
import time
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
        if filename is None:
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
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(self.filename), exist_ok=True)
        
        # Check if file exists
        file_exists = os.path.isfile(self.filename)
        
        self.file = open(self.filename, 'a', newline='')
        self.writer = csv.writer(self.file)
        
        # Write headers only if file is new
        if not file_exists or os.path.getsize(self.filename) == 0:
            self.writer.writerow([
                "Timestamp", "Elapsed (s)", "Pressure (bar)", "Temperature (°C)",
                "Level (m)", "Volume (L)", "Flow Rate (L/min)", "Fill (%)", "Status"
            ])
        
        logger.info(f"Data logging initialized to {self.filename}")
    
    def log_measurement(self, measurements):
        """
        Log a measurement to the CSV file
        
        Args:
            measurements: Dictionary with measurement values
        """
        if not self.writer or not measurements:
            return
        
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
        status = measurements.get('status', 0)
        
        # Write row
        self.writer.writerow([
            timestamp, f"{elapsed:.1f}", f"{pressure:.4f}", 
            f"{temperature:.2f}" if temperature is not None else "N/A",
            f"{level:.3f}", f"{volume:.1f}", f"{flow_rate:.2f}", f"{fill_percent:.1f}",
            f"{status}"
        ])
        
        # Flush to ensure data is written
        self.file.flush()
    
    def close(self):
        """Close the log file"""
        if self.file:
            self.file.close()
            self.file = None
            self.writer = None
            logger.info(f"Data logging to {self.filename} completed")
