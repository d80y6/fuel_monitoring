"""
Tank Monitor

This module provides the TankMonitor class for monitoring a single tank.
"""
import logging
import time
import math
from threading import Lock
from datetime import datetime
from models.database import db, Tank, Measurement
from models.tank_config import TankConfig
from models.tank_sensor_connection import TankSensorConnection
from models.measurement_processor import MeasurementProcessor
from models.statistics_tracker import StatisticsTracker
from models.alarm_manager import AlarmManager
from utils.circuit_breaker import CircuitBreaker
from contextlib import contextmanager
from models.flow_rate_calculator import FlowRateCalculator

# Configure logging
logger = logging.getLogger(__name__)


@contextmanager
def session_scope(app):
    """Provide a transactional scope around a series of operations."""
    with app.app_context():
        try:
            yield
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Database error: {str(e)}")
            raise
        finally:
            db.session.close()


class DatabaseService:
    def __init__(self, app, db):
        self.app = app
        self.db = db

    def save_measurement(self, tank_id, measurement_data):
        with self.app.app_context():
            try:
                measurement = Measurement(
                    tank_id=tank_id,
                    timestamp=measurement_data['timestamp'],
                    pressure=measurement_data['pressure'],
                    temperature=measurement_data['temperature'],
                    level=measurement_data['level'],
                    volume=measurement_data['volume'],
                    flow_rate=measurement_data['flow_rate'],
                    fill_percent=measurement_data['fill_percent'],
                    status=measurement_data['status']
                )

                tank = self.db.session.get(Tank, tank_id)
                if tank:
                    tank.last_connection = datetime.utcnow()
                    tank.connection_status = 'connected'

                self.db.session.add(measurement)
                self.db.session.commit()

                return measurement.to_dict()
            except Exception as e:
                self.db.session.rollback()
                logger.error(f"Database error: {str(e)}")
                return measurement_data


class TankMonitor:
    """
    Tank Monitor class for monitoring a single tank.

    This class handles the connection to the tank sensor and processes measurements.
    """

    def __init__(self, tank_id, app, thread_class, db_service=None):
        """Initialize the tank monitor."""
        self.tank_id = tank_id
        self.app = app
        self.Thread = thread_class
        self.db_service = db_service or DatabaseService(app, db)
        self.monitoring = False
        self.lock = Lock()

        # Load configuration once
        with app.app_context():
            tank = db.session.get(Tank, tank_id)
            if not tank:
                raise ValueError(f"Tank with ID {tank_id} not found in database")

        # Create unified tank configuration
        self.config = TankConfig.from_database(tank, app.config)

        # Store alarm thresholds
        self.alarm_thresholds = {
            'low_level_threshold': tank.low_level_threshold,
            'critical_level_threshold': tank.critical_level_threshold,
            'high_level_threshold': tank.high_level_threshold
        }

        # Initialize components with the unified config
        self.connection = TankSensorConnection(
            self.config.host,
            self.config.tcp_port,
            int(self.config.device_address),
            self.config.max_reconnect_attempts,
            self.config.reconnect_delay_base
        )

        # Initialize measurement processor with tank config (has its own smooth_pressure)
        self.processor = MeasurementProcessor(self.config)

        # Initialize statistics tracker with tank config
        self.statistics = StatisticsTracker(tank_config=self.config)

        # Create circuit breaker for sensor connection
        self.circuit_breaker = CircuitBreaker(
            f"tank_{tank_id}_sensor",
            failure_threshold=3,
            recovery_timeout=30
        )

        # Initialize flow rate calculator
        self.flow_calculator = FlowRateCalculator(
            max_history_points=5,
            min_significant_change=5.0,
            smoothing_factor=0.5,
            expected_max_inflow_rate=600.0,
            expected_max_outflow_rate=100.0,
            refill_detection_threshold=100.0
        )

    def load_config(self):
        """Load tank configuration from database."""
        with self.app.app_context():
            tank = db.session.get(Tank, self.tank_id)
            if not tank:
                raise ValueError(f"Tank with ID {self.tank_id} not found")

            self.config = TankConfig.from_database(tank, self.app.config)

            self.alarm_thresholds = {
                'low_level_threshold': tank.low_level_threshold,
                'critical_level_threshold': tank.critical_level_threshold,
                'high_level_threshold': tank.high_level_threshold
            }

    def connect(self):
        """Connect to the tank sensor."""
        if not self.circuit_breaker.allow_request():
            logger.warning(f"Circuit breaker preventing connection to tank {self.tank_id}")
            return False

        result = self.connection.connect()

        if result:
            with session_scope(self.app):
                tank = db.session.get(Tank, self.tank_id)
                if tank:
                    tank.last_connection = datetime.utcnow()
                    tank.connection_status = 'connected'

            self.circuit_breaker.on_success()
        else:
            self.circuit_breaker.on_failure()

        return result

    def disconnect(self):
        """Disconnect from the tank sensor."""
        result = self.connection.disconnect()

        if result:
            with session_scope(self.app):
                tank = db.session.get(Tank, self.tank_id)
                if tank:
                    tank.connection_status = 'disconnected'

        return result

    def read_measurement(self):
        """Read a measurement from the tank sensor."""
        if not self._ensure_connection():
            return None

        try:
            sensor_data = self._read_sensor_data()
            if not sensor_data:
                return None

            # Delegate pressure smoothing to the MeasurementProcessor
            if self.config.pressure_smoothing:
                smoothed_pressure = self.processor.smooth_pressure(sensor_data['pressure'])
                sensor_data['pressure'] = smoothed_pressure

            # Process measurement
            measurement_data = self.processor.process_measurement(
                sensor_data['pressure'],
                sensor_data['temperature'],
                sensor_data['status']
            )

            # Calculate flow rate and update statistics
            measurement_data = self._calculate_flow_and_statistics(measurement_data)

            # Save measurement to database and check alarms
            return self._save_measurement_and_check_alarms(measurement_data)

        except Exception as e:
            logger.error(f"Unexpected error reading from tank {self.tank_id}: {str(e)}")
            return None

    def _ensure_connection(self):
        """Ensure connection to sensor is established."""
        if not self.circuit_breaker.allow_request():
            logger.warning(f"Circuit breaker preventing operation for tank {self.tank_id}")
            return False

        if self.connection.connected:
            return True

        logger.info(f"Attempting to connect to tank {self.tank_id}")
        if self.connection.connect():
            with self.app.app_context():
                tank = db.session.get(Tank, self.tank_id)
                if tank:
                    tank.last_connection = datetime.utcnow()
                    tank.connection_status = 'connected'

            self.circuit_breaker.on_success()
            return True
        else:
            self.circuit_breaker.on_failure()
            return False

    def _read_sensor_data(self):
        """Read all sensor data at once."""
        try:
            pressure_result = self.connection.read_channel_float(self.config.pressure_channel)
            if not pressure_result:
                logger.error(f"Failed to read pressure for tank {self.tank_id}")
                self.circuit_breaker.on_failure()
                return None

            pressure = round(pressure_result['value'], 5)
            status = pressure_result['status']

            temperature = None
            try:
                time.sleep(1)
                temp_result = self.connection.read_channel_float(self.config.temp_channel)
                if temp_result and not math.isnan(temp_result['value']):
                    temperature = round(temp_result['value'], 1)
            except Exception as e:
                logger.debug(f"Temperature reading failed: {str(e)}")

            self.circuit_breaker.on_success()

            return {
                'pressure': pressure,
                'temperature': temperature,
                'status': status
            }
        except Exception as e:
            logger.error(f"Error reading sensor data: {str(e)}")
            self.circuit_breaker.on_failure()
            return None

    def start_monitoring(self):
        """Start monitoring the tank."""
        with self.lock:
            if self.monitoring:
                return True

            if not self.connection.connected and not self.connect():
                logger.error(f"Failed to connect to tank {self.tank_id}, will retry in monitoring thread")

            self.monitoring = True

            if self.Thread is not None:
                try:
                    thread = self.Thread(target=self._monitor_thread, daemon=True)
                    thread.start()
                    return True
                except Exception as e:
                    logger.error(f"Failed to start monitoring thread for tank {self.tank_id}: {str(e)}")
                    self.monitoring = False
                    return False
            else:
                logger.error(f"Thread class not available for tank {self.tank_id}")
                self.monitoring = False
                return False

    def stop_monitoring(self):
        """Stop monitoring the tank."""
        with self.lock:
            if not self.monitoring:
                return True

            self.monitoring = False

            if self.connection.connected:
                self.disconnect()

            return True

    def _monitor_thread(self):
        """Main monitoring thread function."""
        logger.info(f"Started monitoring tank {self.tank_id}")
        consecutive_failures = 0
        max_consecutive_failures = 5

        update_interval = self.app.config.get('UPDATE_INTERVAL', 60)
        logger.info(f"Tank {self.tank_id} monitoring with update interval of {update_interval} seconds")

        while self.monitoring:
            consecutive_failures = self._execute_measurement_cycle(
                consecutive_failures,
                max_consecutive_failures,
                update_interval
            )

        logger.info(f"Stopped monitoring tank {self.tank_id}")

    def _execute_measurement_cycle(self, consecutive_failures, max_consecutive_failures, update_interval):
        """Execute a single measurement cycle and handle results."""
        try:
            start_time = time.time()

            measurement = self.read_measurement()

            if measurement:
                self._handle_successful_measurement(measurement)
                consecutive_failures = 0
            else:
                consecutive_failures = self._handle_failed_measurement(consecutive_failures, max_consecutive_failures)

            self._wait_for_next_cycle(start_time, update_interval)

        except Exception as e:
            logger.error(f"Error in monitor thread for tank {self.tank_id}: {str(e)}")
            consecutive_failures += 1
            time.sleep(5)

        return consecutive_failures

    def _handle_successful_measurement(self, measurement):
        """Handle a successful measurement."""
        logger.debug(f"Emitting measurement for tank {self.tank_id}: {measurement}")

    def _handle_failed_measurement(self, consecutive_failures, max_consecutive_failures):
        """Handle a failed measurement and return updated failure count."""
        consecutive_failures += 1
        logger.warning(f"Failed to read measurement from tank {self.tank_id} "
                      f"({consecutive_failures}/{max_consecutive_failures})")

        if consecutive_failures >= max_consecutive_failures:
            logger.error(f"Too many consecutive failures for tank {self.tank_id}, reconnecting")
            self.disconnect()
            time.sleep(5)
            if self.connect():
                return 0
            else:
                time.sleep(30)

        return consecutive_failures

    def _wait_for_next_cycle(self, start_time, update_interval):
        """Wait for the next measurement cycle."""
        elapsed_time = time.time() - start_time
        sleep_time = max(0, update_interval - elapsed_time)

        logger.info(f"Tank {self.tank_id}: Measurement cycle took {elapsed_time:.2f}s, sleeping for {sleep_time:.2f}s")

        time.sleep(sleep_time)

    def _calculate_flow_and_statistics(self, measurement_data):
        """Calculate flow rate and update statistics for a measurement."""
        try:
            latest = self._get_latest_measurement()

            flow_rate = 0.0
            if 'volume' in measurement_data:
                volume_stable = False
                if latest and 'volume' in latest:
                    prev_volume = latest['volume']
                    curr_volume = measurement_data['volume']

                    if abs(curr_volume - prev_volume) < 0.5:
                        if self.flow_calculator.current_flow_rate != 0:
                            decayed_rate = self.flow_calculator.current_flow_rate * 0.3
                            flow_rate = 0.0 if abs(decayed_rate) < 1.0 else decayed_rate
                            logger.debug(f"Stable volume detected for tank {self.tank_id}. Decaying flow rate to {flow_rate:.2f}")
                        else:
                            flow_rate = 0.0
                    else:
                        flow_rate = self.flow_calculator.add_measurement(
                            measurement_data['volume'],
                            measurement_data['timestamp']
                        )
                else:
                    flow_rate = self.flow_calculator.add_measurement(
                        measurement_data['volume'],
                        measurement_data['timestamp']
                    )

            measurement_data['flow_rate'] = flow_rate

            self.statistics.update_statistics(measurement_data)

            return measurement_data
        except Exception as e:
            logger.error(f"Error calculating flow rate: {str(e)}")
            if 'flow_rate' not in measurement_data:
                measurement_data['flow_rate'] = 0.0
            return measurement_data

    def _get_latest_measurement(self):
        """Get the latest measurement from the database for this tank."""
        try:
            with self.app.app_context():
                tank = db.session.get(Tank, self.tank_id)
                if not tank:
                    logger.warning(f"Tank with ID {self.tank_id} not found when getting latest measurement")
                    return None

                latest_measurement = tank.get_latest_measurement() if hasattr(tank, 'get_latest_measurement') else None

                if latest_measurement is None and not hasattr(tank, 'get_latest_measurement'):
                    latest_measurement = Measurement.query.filter_by(tank_id=self.tank_id).order_by(
                        Measurement.timestamp.desc()).first()

                if latest_measurement:
                    return latest_measurement.to_dict() if hasattr(latest_measurement, 'to_dict') else latest_measurement
                return None
        except Exception as e:
            logger.error(f"Error getting latest measurement for tank {self.tank_id}: {str(e)}")
            return None

    def _save_measurement_and_check_alarms(self, measurement_data):
        """Save measurement data to database and check for alarms."""
        try:
            measurement_dict = self.db_service.save_measurement(self.tank_id, measurement_data)
            self._check_measurement_alarms(measurement_data)
            return measurement_dict
        except Exception as e:
            logger.error(f"Error saving measurement to database for tank {self.tank_id}: {str(e)}")
            return measurement_data

    def _check_measurement_alarms(self, measurement_data):
        """Check for alarms based on measurement data."""
        alarm_manager = AlarmManager(self.tank_id, db.session, app=self.app)
        alarm_manager.check_alarms(measurement_data, self.alarm_thresholds)

    def get_statistics(self):
        """Get statistics for the tank."""
        stats = self.statistics.get_statistics()
        stats['tank_id'] = self.tank_id
        return stats

    def reset_statistics(self):
        """Reset statistics for the tank."""
        return self.statistics.reset_statistics()

    def calibrate(self, known_volume):
        """Calibrate the tank based on a known volume."""
        try:
            if not self.connection.connected:
                logger.warning(f"Cannot calibrate tank {self.tank_id}: Not connected")
                if not self.connect():
                    return None

            with session_scope(self.app):
                pressure_result = self.connection.read_channel_float(self.config.pressure_channel)
                if not pressure_result:
                    logger.error(f"Failed to read pressure for calibration")
                    return None

                pressure = round(pressure_result['value'], 5)

                temperature = None
                try:
                    temp_result = self.connection.read_channel_float(self.config.temp_channel)
                    if temp_result and not math.isnan(temp_result['value']):
                        temperature = round(temp_result['value'], 1)
                except Exception as e:
                    logger.debug(f"Temperature reading failed during calibration: {str(e)}")

                old_calibration = self.config.calibration_factor
                self.config.calibration_factor = 1.0
                level = self.processor.pressure_to_level(pressure, temperature)

                raw_volume = self.processor.calculate_volume_from_level(level)

                if raw_volume > 0:
                    new_factor = known_volume / raw_volume
                else:
                    logger.error(f"Cannot calibrate: uncalibrated volume is zero or negative")
                    self.config.calibration_factor = old_calibration
                    return None

                self.config.calibration_factor = new_factor

                tank = db.session.get(Tank, self.tank_id)
                if tank:
                    tank.calibration_factor = new_factor
                    db.session.commit()

                logger.info(f"Calibrated tank {self.tank_id}: new factor = {new_factor}")
                return new_factor
        except Exception as e:
            logger.error(f"Failed to calibrate tank {self.tank_id}: {str(e)}")
            return None

    def cleanup_resources(self):
        """Clean up resources to prevent memory leaks."""
        with self.lock:
            if self.connection.connected:
                self.disconnect()

            self.connection.client = None

            logger.info(f"Resources cleaned up for tank {self.tank_id}")
            return True

    def _get_level_hysteresis(self, tank_config):
        """Calculate appropriate level hysteresis based on tank size."""
        with self.app.app_context():
            tank = db.session.get(Tank, self.tank_id)
            if tank and hasattr(tank, 'level_hysteresis') and tank.level_hysteresis is not None:
                return tank.level_hysteresis

        tank_volume_liters = tank_config.tank_volume * 1000
        return 0.005 if tank_volume_liters > 50000 else 0.002
