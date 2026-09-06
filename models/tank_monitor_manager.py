"""
Tank Monitor Manager

This module provides the TankMonitorManager class for managing multiple tank monitors.
"""
import logging
import threading
from models.database import db, Tank
from models.tank_monitor import TankMonitor

logger = logging.getLogger(__name__)

class TankMonitorManager:
    """Manage multiple tank monitors."""
    
    def __init__(self, app):
        """
        Initialize the tank monitor manager.
        
        Args:
            app: Flask application
        """
        self.app = app
        self.monitors = {}
        self.lock = threading.Lock()
    
    def initialize_monitors(self):
        """Initialize monitors for all active tanks."""
        with self.app.app_context():
            # Get all active tanks
            tanks = Tank.query.filter_by(is_active=True, deleted_at=None).all()
            
            for tank in tanks:
                self.add_monitor(tank.id)
            
            logger.info(f"Initialized {len(self.monitors)} tank monitors")
    
    def add_monitor(self, tank_id):
        """
        Add a monitor for a tank.
        
        Args:
            tank_id: ID of the tank
            
        Returns:
            bool: True if successful, False otherwise
        """
        with self.lock:
            # Check if monitor already exists
            if tank_id in self.monitors:
                logger.warning(f"Monitor for tank {tank_id} already exists")
                return False
            
            try:
                # Create monitor
                monitor = TankMonitor(tank_id, self.app, threading.Thread)
                
                # Store monitor
                self.monitors[tank_id] = monitor
                
                logger.info(f"Added monitor for tank {tank_id}")
                return True
                
            except Exception as e:
                logger.error(f"Error adding monitor for tank {tank_id}: {str(e)}")
                return False
    
    def remove_monitor(self, tank_id):
        """
        Remove a monitor for a tank.
        
        Args:
            tank_id: ID of the tank
            
        Returns:
            bool: True if successful, False otherwise
        """
        with self.lock:
            # Check if monitor exists
            if tank_id not in self.monitors:
                logger.warning(f"No monitor exists for tank {tank_id}")
                return False
            
            try:
                # Stop monitoring
                self.stop_monitoring(tank_id)
                
                # Clean up resources
                self.monitors[tank_id].cleanup_resources()
                
                # Remove monitor
                del self.monitors[tank_id]
                
                logger.info(f"Removed monitor for tank {tank_id}")
                return True
                
            except Exception as e:
                logger.error(f"Error removing monitor for tank {tank_id}: {str(e)}")
                return False
    
    def start_monitoring(self, tank_id=None):
        """
        Start monitoring for a tank or all tanks.
        
        Args:
            tank_id: ID of the tank or None for all tanks
            
        Returns:
            bool: True if successful, False otherwise
        """
        with self.lock:
            if tank_id is not None:
                # Start monitoring for a single tank
                if tank_id not in self.monitors:
                    logger.warning(f"No monitor exists for tank {tank_id}")
                    return False
                
                return self.monitors[tank_id].start_monitoring()
            else:
                # Start monitoring for all tanks
                success = True
                for tank_id, monitor in self.monitors.items():
                    if not monitor.start_monitoring():
                        success = False
                
                return success
    
    # Add this method to match what's called in app.py
    def start_monitoring_all_active_tanks(self):
        """
        Start monitoring for all active tanks.
        
        Returns:
            bool: True if successful, False otherwise
        """
        # This is just an alias for start_monitoring() with no tank_id
        return self.start_monitoring()
    
    def stop_monitoring(self, tank_id=None):
        """
        Stop monitoring for a tank or all tanks.
        
        Args:
            tank_id: ID of the tank or None for all tanks
            
        Returns:
            bool: True if successful, False otherwise
        """
        with self.lock:
            if tank_id is not None:
                # Stop monitoring for a single tank
                if tank_id not in self.monitors:
                    logger.warning(f"No monitor exists for tank {tank_id}")
                    return False
                
                return self.monitors[tank_id].stop_monitoring()
            else:
                # Stop monitoring for all tanks
                success = True
                for tank_id, monitor in self.monitors.items():
                    if not monitor.stop_monitoring():
                        success = False
                
                return success
    
    def get_monitor(self, tank_id):
        """
        Get a monitor for a tank.
        
        Args:
            tank_id: ID of the tank
            
        Returns:
            TankMonitor: Monitor for the tank or None if not found
        """
        return self.monitors.get(tank_id)
    
    def read_measurement(self, tank_id):
        """
        Read a measurement from a tank.
        
        Args:
            tank_id: ID of the tank
            
        Returns:
            dict: Measurement data or None if error
        """
        monitor = self.get_monitor(tank_id)
        
        if not monitor:
            logger.warning(f"No monitor exists for tank {tank_id}")
            return None
        
        return monitor.read_measurement()
    
    def cleanup_resources(self):
        """Clean up all monitors."""
        with self.lock:
            # Stop monitoring for all tanks
            self.stop_monitoring()
            
            # Clean up resources for all monitors
            for tank_id, monitor in list(self.monitors.items()):
                monitor.cleanup_resources()
                del self.monitors[tank_id]
            
            logger.info("Cleaned up all tank monitors")
