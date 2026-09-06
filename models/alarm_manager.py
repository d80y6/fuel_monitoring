"""
Alarm Manager

This module provides the AlarmManager class for managing tank alarms.
"""
import logging
from datetime import datetime, timedelta
from models.database import Alarm

logger = logging.getLogger(__name__)

# Cooldown period per alarm type (seconds) to prevent duplicate alarms
ALARM_COOLDOWNS = {
    'low_level': 300,
    'critical_level': 300,
    'high_level': 300,
    'sensor_error': 60,
    'connection_lost': 300,
}


class AlarmManager:
    """Manage alarms for a tank."""

    def __init__(self, tank_id, db_session, app=None):
        self.tank_id = tank_id
        self.db_session = db_session
        self.app = app
        self._last_alarm_times = {}

    def check_alarms(self, measurement_data, thresholds):
        """Check for alarm conditions based on measurement data."""
        if self.app:
            with self.app.app_context():
                return self._check_alarms_impl(measurement_data, thresholds)
        else:
            return self._check_alarms_impl(measurement_data, thresholds)

    def _check_alarms_impl(self, measurement_data, thresholds):
        triggered_alarms = []

        fill_percent = measurement_data.get('fill_percent')
        status = measurement_data.get('status')

        if fill_percent is not None:
            if fill_percent <= thresholds.get('low_level_threshold', 20) and fill_percent > thresholds.get('critical_level_threshold', 10):
                alarm = self._create_alarm('low_level', 'warning', f'Tank level is low: {fill_percent:.1f}%', fill_percent)
                if alarm:
                    triggered_alarms.append(alarm)

            if fill_percent <= thresholds.get('critical_level_threshold', 10):
                alarm = self._create_alarm('critical_level', 'danger', f'Tank level is critical: {fill_percent:.1f}%', fill_percent)
                if alarm:
                    triggered_alarms.append(alarm)

            if fill_percent >= thresholds.get('high_level_threshold', 90):
                alarm = self._create_alarm('high_level', 'warning', f'Tank level is high: {fill_percent:.1f}%', fill_percent)
                if alarm:
                    triggered_alarms.append(alarm)

        if status is not None and status != 0:
            error_message = f'Sensor error: Status code {status}'
            alarm = self._create_alarm('sensor_error', 'danger', error_message, status)
            if alarm:
                triggered_alarms.append(alarm)

        return triggered_alarms

    def _create_alarm(self, alarm_type, level, message, value):
        """Create an alarm record if cooldown has elapsed since the last alarm of this type."""
        now = datetime.utcnow()

        last_time = self._last_alarm_times.get(alarm_type)
        cooldown = ALARM_COOLDOWNS.get(alarm_type, 300)
        if last_time and (now - last_time).total_seconds() < cooldown:
            logger.debug(f"Alarm {alarm_type} suppressed (cooldown) for tank {self.tank_id}")
            return None

        try:
            alarm = Alarm(
                tank_id=self.tank_id,
                timestamp=now,
                type=alarm_type,
                level=level,
                message=message,
                value=value,
                acknowledged=False
            )

            self.db_session.add(alarm)
            self.db_session.commit()

            self._last_alarm_times[alarm_type] = now
            logger.warning(f"Alarm created for tank {self.tank_id}: {level} - {message}")
            return alarm

        except Exception as e:
            self.db_session.rollback()
            logger.error(f"Error creating alarm for tank {self.tank_id}: {str(e)}")
            return None

    def acknowledge_alarm(self, alarm_id, user_id=None):
        """Acknowledge an alarm."""
        try:
            alarm = self.db_session.get(Alarm, alarm_id)

            if not alarm:
                logger.warning(f"Alarm with ID {alarm_id} not found")
                return False

            if alarm.tank_id != self.tank_id:
                logger.warning(f"Alarm with ID {alarm_id} does not belong to tank {self.tank_id}")
                return False

            alarm.acknowledged = True
            alarm.acknowledged_at = datetime.utcnow()
            alarm.acknowledged_by = user_id

            self.db_session.commit()

            logger.info(f"Alarm {alarm_id} acknowledged by user {user_id}")
            return True

        except Exception as e:
            self.db_session.rollback()
            logger.error(f"Error acknowledging alarm {alarm_id}: {str(e)}")
            return False

    def get_active_alarms(self):
        """Get active (unacknowledged) alarms for the tank."""
        try:
            alarms = self.db_session.query(Alarm).filter_by(
                tank_id=self.tank_id,
                acknowledged=False
            ).order_by(Alarm.timestamp.desc()).all()

            return alarms

        except Exception as e:
            logger.error(f"Error getting active alarms for tank {self.tank_id}: {str(e)}")
            return []
