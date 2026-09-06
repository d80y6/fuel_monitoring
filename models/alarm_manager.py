"""
Alarm Manager

This module provides the AlarmManager class for managing tank alarms.
"""
import logging
from datetime import datetime
from models.database import Alarm

logger = logging.getLogger(__name__)

class AlarmManager:
    """Manage alarms for a tank."""
    
    def __init__(self, tank_id, db_session, app=None):
        """
        Initialize the alarm manager.
        
        Args:
            tank_id: ID of the tank
            db_session: Database session
            app: Flask application instance (optional)
        """
        self.tank_id = tank_id
        self.db_session = db_session
        self.app = app
    
    def check_alarms(self, measurement_data, thresholds):
        """
        Check for alarm conditions based on measurement data.
        
        Args:
            measurement_data: Dictionary with measurement data
            thresholds: Dictionary with alarm thresholds
            
        Returns:
            list: List of triggered alarms
        """
        # If we have an app instance, use its context
        if self.app:
            with self.app.app_context():
                return self._check_alarms_impl(measurement_data, thresholds)
        else:
            # Otherwise try to use the current context
            return self._check_alarms_impl(measurement_data, thresholds)
    
    def _check_alarms_impl(self, measurement_data, thresholds):
        triggered_alarms = []
        
        # Extract values
        fill_percent = measurement_data.get('fill_percent')
        status = measurement_data.get('status')
        
        # Check for low level alarm
        if fill_percent <= thresholds.get('low_level_threshold', 20) and fill_percent > thresholds.get('critical_level_threshold', 10):
            alarm = self._create_alarm('low_level', f'Tank level is low: {fill_percent:.1f}%', fill_percent)
            if alarm:
                triggered_alarms.append(alarm)
        
        # Check for critical level alarm
        if fill_percent <= thresholds.get('critical_level_threshold', 10):
            alarm = self._create_alarm('critical_level', f'Tank level is critical: {fill_percent:.1f}%', fill_percent)
            if alarm:
                triggered_alarms.append(alarm)
        
        # Check for high level alarm
        if fill_percent >= thresholds.get('high_level_threshold', 90):
            alarm = self._create_alarm('high_level', f'Tank level is high: {fill_percent:.1f}%', fill_percent)
            if alarm:
                triggered_alarms.append(alarm)
        
        # Check for sensor errors
        if status != 0:
            # Interpret status bits
            error_message = f'Sensor error: Status code {status}'
            alarm = self._create_alarm('sensor_error', error_message, status)
            if alarm:
                triggered_alarms.append(alarm)
        
        return triggered_alarms
    
    def _create_alarm(self, alarm_type, message, value):
        """
        Create an alarm record if a similar unacknowledged alarm doesn't exist.
        
        Args:
            alarm_type: Type of alarm
            message: Alarm message
            value: Value that triggered the alarm
            
        Returns:
            Alarm: Created alarm or None if not created
        """
        try:
            # Import Flask's current_app to check if we're in an application context
            from flask import current_app
            
            # Use the db session that was passed to the constructor
            # instead of importing it here
            alarm = Alarm(
                tank_id=self.tank_id,
                timestamp=datetime.now(),
                type=alarm_type,
                message=message,
                value=value,
                acknowledged=False
            )
            
            self.db_session.add(alarm)
            self.db_session.commit()
            
            logger.warning(f"Alarm created for tank {self.tank_id}: {message}")
            return alarm
            
        except Exception as e:
            logger.error(f"Error creating alarm for tank {self.tank_id}: {str(e)}")
            return None
    
    def acknowledge_alarm(self, alarm_id, user_id=None):
        """
        Acknowledge an alarm.
        
        Args:
            alarm_id: ID of the alarm
            user_id: ID of the user acknowledging the alarm (optional)
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            alarm = Alarm.query.get(alarm_id)
            
            if not alarm:
                logger.warning(f"Alarm with ID {alarm_id} not found")
                return False
            
            if alarm.tank_id != self.tank_id:
                logger.warning(f"Alarm with ID {alarm_id} does not belong to tank {self.tank_id}")
                return False
            
            # Update alarm
            alarm.acknowledged = True
            alarm.acknowledged_at = datetime.now()
            alarm.acknowledged_by = user_id
            
            # Save to database
            self.db_session.commit()
            
            logger.info(f"Alarm {alarm_id} acknowledged by user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error acknowledging alarm {alarm_id}: {str(e)}")
            return False
    
    def get_active_alarms(self):
        """
        Get active (unacknowledged) alarms for the tank.
        
        Returns:
            list: List of active alarms
        """
        try:
            alarms = Alarm.query.filter_by(
                tank_id=self.tank_id,
                acknowledged=False
            ).order_by(Alarm.timestamp.desc()).all()
            
            return alarms
            
        except Exception as e:
            logger.error(f"Error getting active alarms for tank {self.tank_id}: {str(e)}")
            return []
