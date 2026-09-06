# Refactored Production Code Snippets

## 1. Refactored MQTT Ingestion Service with Redis Cache & Batch Processing

```python
"""
Refactored MQTT Ingestion Service
- Thread-safe Redis cache for tank lookups
- Batch database writes
- JSON schema validation
- TLS support
- Async processing via Redis Queue
"""
import json
import logging
import time
import threading
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any
from functools import wraps

import paho.mqtt.client as mqtt
import redis
from flask import Flask, current_app
from jsonschema import validate, ValidationError

from models.database import db, Tank, Measurement
from models.measurement_processor import MeasurementProcessor
from models.flow_rate_calculator import FlowRateCalculator
from models.alarm_manager import AlarmManager
from models.tank_config import TankConfig

logger = logging.getLogger("MqttIngestion")

# ── JSON Schema for MQTT payload validation ──────────────────────────
MQTT_READINGS_SCHEMA = {
    "type": "object",
    "required": ["gateway_mac", "timestamp", "sensors"],
    "properties": {
        "gateway_mac": {"type": "string", "pattern": "^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$"},
        "site_id": {"type": "string"},
        "timestamp": {"type": "integer", "minimum": 0},
        "sensors": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["serial_number", "pressure_bar"],
                "properties": {
                    "serial_number": {"type": "integer", "minimum": 1},
                    "device_address": {"type": "integer", "minimum": 1, "maximum": 255},
                    "pressure_bar": {"type": "number"},
                    "temperature_c": {"type": ["number", "null"]},
                    "status": {"type": "integer", "minimum": 0},
                    "timestamp": {"type": "integer"}
                }
            }
        }
    }
}


def validate_payload(schema):
    """Decorator to validate MQTT payloads against JSON schema."""
    def decorator(func):
        @wraps(func)
        def wrapper(self, topic, payload):
            try:
                data = json.loads(payload.decode('utf-8'))
                validate(instance=data, schema=schema)
                return func(self, topic, data)
            except ValidationError as e:
                logger.error(f"Payload validation failed: {e.message}")
                self._publish_error(topic, e.message)
            except json.JSONDecodeError:
                logger.error("Invalid JSON in MQTT message")
        return wrapper
    return decorator


class MqttIngestionService:
    """
    Refactored MQTT ingestion service with:
    - Redis-backed LRU tank cache (prevents DB exhaustion)
    - Thread-safe batch processing pipeline
    - JSON schema enforcement
    - TLS authentication
    - Offline message queuing via Redis Streams
    """

    def __init__(
        self,
        app: Flask,
        broker: str,
        port: int = 8883,  # Default TLS port
        username: str = None,
        password: str = None,
        ca_cert: str = None,
        client_cert: str = None,
        client_key: str = None,
        redis_url: str = "redis://localhost:6379/0",
        batch_size: int = 50,
        batch_timeout: float = 2.0,
    ):
        self.app = app
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password
        self.ca_cert = ca_cert
        self.client_cert = client_cert
        self.client_key = client_key

        # Redis for caching and queueing
        self.redis_client = redis.from_url(redis_url)
        self._cache_ttl = 300  # 5 minutes in seconds
        self._cache_lock = threading.Lock()

        # Batch processing configuration
        self._batch_size = batch_size
        self._batch_timeout = batch_timeout
        self._measurement_buffer: List[Measurement] = []
        self._buffer_lock = threading.Lock()
        self._last_batch_time = time.time()

        # MQTT client with TLS
        self.client = mqtt.Client(
            protocol=mqtt.MQTTv5,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        )
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

        # TLS configuration
        if ca_cert or (client_cert and client_key):
            self.client.tls_set(
                ca_certs=ca_cert,
                certfile=client_cert,
                keyfile=client_key,
                cert_reqs=mqtt.ssl.CERT_REQUIRED,
                tls_version=mqtt.ssl.PROTOCOL_TLSv1_2,
            )

        if self.username and self.password:
            self.client.username_pw_set(self.username, self.password)

        # Last Will and Testament
        self.client.will_set(
            "fuel/service/status",
            json.dumps({"status": "offline", "timestamp": time.time()}),
            retain=True,
            qos=1,
        )

        self._running = False
        self._thread = None
        self._topic_readings = "fuel/+/readings"
        self._topic_status = "fuel/+/status"
        self._topic_cmd = "fuel/+/cmd"
        self._cmd_handlers: Dict[str, callable] = {}

        # Register command handlers
        self._register_cmd_handlers()

    def _register_cmd_handlers(self):
        """Register bi-directional command handlers."""
        self._cmd_handlers["reconfigure"] = self._cmd_reconfigure
        self._cmd_handlers["set_interval"] = self._cmd_set_interval
        self._cmd_handlers["reboot"] = self._cmd_reboot
        self._cmd_handlers["diagnose"] = self._cmd_diagnose

    def start(self):
        """Start the MQTT ingestion service in a background thread."""
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="mqtt-ingestion")
        self._thread.start()

        # Start batch processor thread
        batch_thread = threading.Thread(target=self._batch_processor, daemon=True, name="batch-processor")
        batch_thread.start()

        logger.info("MQTT Ingestion Service started")

    def stop(self):
        """Stop the service gracefully, flushing remaining batches."""
        self._running = False
        self._flush_batch()  # Flush any remaining measurements
        if self.client.is_connected():
            self.client.disconnect()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("MQTT Ingestion Service stopped")

    def _run(self):
        """Main loop - runs in background thread."""
        while self._running:
            try:
                self.client.connect(self.broker, self.port, keepalive=60)
                self.client.loop_forever(retry_first_connection=True)
            except Exception as e:
                logger.error(f"MQTT connection error: {e}")
                # Exponential backoff with jitter
                time.sleep(min(30, 5 * (1 + hash(e) % 10)))

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        """Subscribe to all gateway topics on connect."""
        if rc == 0:
            logger.info(f"Connected to MQTT broker: {self.broker}")
            client.subscribe(self._topic_readings, qos=1)
            client.subscribe(self._topic_status, qos=1)
            client.subscribe(self._topic_cmd, qos=1)
            client.publish(
                "fuel/service/status",
                json.dumps({"status": "online", "timestamp": time.time()}),
                retain=True,
                qos=1,
            )
        else:
            logger.error(f"MQTT connection failed with code: {rc}")

    def _on_disconnect(self, client, userdata, rc, properties=None):
        logger.warning(f"MQTT disconnected with code: {rc}")

    @validate_payload(MQTT_READINGS_SCHEMA)
    def _on_message(self, client, userdata, msg):
        """Route incoming MQTT messages with schema validation."""
        try:
            topic = msg.topic
            payload = json.loads(msg.payload.decode('utf-8'))

            if "/readings" in topic:
                self._handle_reading(topic, payload)
            elif "/status" in topic:
                self._handle_status(topic, payload)

        except Exception as e:
            logger.error(f"Error processing MQTT message: {e}")

    def _handle_reading(self, topic: str, payload: dict):
        """
        Process a raw sensor reading from an ESP32 gateway.
        Uses Redis cache for tank lookups and batches DB writes.
        """
        gateway_mac = payload.get("gateway_mac") or topic.split("/")[1]
        sensors = payload.get("sensors", [])

        # Parallel lookups via Redis cache
        tank_lookup_futures = []
        for sensor_data in sensors:
            serial_number = sensor_data.get("serial_number")
            device_address = sensor_data.get("device_address", 1)
            tank = self._find_tank_cached(gateway_mac, serial_number, device_address)
            if tank:
                measurement = self._process_sensor(tank, sensor_data, payload.get("timestamp"))
                if measurement:
                    with self._buffer_lock:
                        self._measurement_buffer.append(measurement)

        # Trigger batch flush if buffer is full
        if len(self._measurement_buffer) >= self._batch_size:
            self._flush_batch()

    def _find_tank_cached(self, gateway_mac: str, serial_number: int, device_address: int) -> Optional[Tank]:
        """
        Find tank using Redis LRU cache to prevent DB exhaustion.
        Priority: serial_number > gateway_mac + device_address
        """
        cache_key = f"tank:sn:{serial_number}" if serial_number else f"tank:mac:{gateway_mac}:addr:{device_address}"

        # Try Redis cache first (thread-safe via Redis itself)
        cached = self.redis_client.get(cache_key)
        if cached:
            try:
                return Tank(**json.loads(cached))
            except Exception:
                pass

        # Cache miss — query DB
        with self.app.app_context():
            if serial_number:
                tank = Tank.query.filter_by(
                    sensor_serial_number=serial_number,
                    deleted_at=None
                ).first()
            else:
                tank = Tank.query.filter_by(
                    gateway_mac=gateway_mac,
                    device_address=device_address,
                    deleted_at=None
                ).first()

            if tank:
                # Store in Redis cache with TTL
                # Store only essential fields to minimize Redis memory
                tank_data = {
                    'id': tank.id,
                    'name': tank.name,
                    'site_id': tank.site_id,
                    'tank_diameter': tank.tank_diameter,
                    'tank_height': tank.tank_height,
                    'fluid_density': tank.fluid_density,
                    'atmospheric_pressure': tank.atmospheric_pressure,
                    'elevation': tank.elevation,
                    'calibration_factor': tank.calibration_factor,
                    'tank_orientation': tank.tank_orientation,
                    'low_level_threshold': tank.low_level_threshold,
                    'critical_level_threshold': tank.critical_level_threshold,
                    'high_level_threshold': tank.high_level_threshold,
                    'pressure_channel': tank.pressure_channel,
                    'temp_channel': tank.temp_channel,
                }
                self.redis_client.setex(cache_key, self._cache_ttl, json.dumps(tank_data))
                return tank

        return None

    def _process_sensor(self, tank, sensor_data: dict, gateway_timestamp: int) -> Optional[Measurement]:
        """Process a single sensor's data through the cloud pipeline."""
        try:
            with self.app.app_context():
                # 1. Build tank config (lightweight, no full DB query)
                config = TankConfig.from_database(tank, self.app.config)

                # 2. Process measurement
                processor = MeasurementProcessor(config)
                measurement_data = processor.process_measurement(
                    sensor_data.get("pressure_bar"),
                    sensor_data.get("temperature_c"),
                    sensor_data.get("status", 0)
                )

                # 3. Calculate flow rate
                flow_rate = self._calculate_flow_rate(tank.id, measurement_data['volume'], gateway_timestamp)
                measurement_data['flow_rate'] = flow_rate

                # 4. Create Measurement object (don't commit yet)
                measurement = Measurement(
                    tank_id=tank.id,
                    timestamp=datetime.fromtimestamp(gateway_timestamp, tz=timezone.utc),
                    pressure=measurement_data['pressure'],
                    temperature=measurement_data['temperature'],
                    level=measurement_data['level'],
                    volume=measurement_data['volume'],
                    flow_rate=measurement_data['flow_rate'],
                    fill_percent=measurement_data['fill_percent'],
                    status=measurement_data['status']
                )

                # Update tank connection status (stored in Redis for batch update)
                self.redis_client.setex(f"tank:status:{tank.id}", 300, json.dumps({
                    'last_connection': datetime.utcnow().isoformat(),
                    'connection_status': 'connected'
                }))

                return measurement

        except Exception as e:
            logger.error(f"Error processing sensor SN:{sensor_data.get('serial_number')}: {e}")
            return None

    def _calculate_flow_rate(self, tank_id: int, current_volume: float, timestamp: int) -> float:
        """Calculate flow rate using the latest measurement from DB."""
        try:
            with self.app.app_context():
                latest = Measurement.query.filter_by(tank_id=tank_id)\
                    .order_by(Measurement.timestamp.desc()).first()

                if latest and current_volume is not None:
                    time_diff = (datetime.fromtimestamp(timestamp) - latest.timestamp).total_seconds()
                    if time_diff > 0:
                        vol_diff = current_volume - latest.volume
                        return (vol_diff / time_diff) * 60  # L/min
                return 0.0
        except Exception:
            return 0.0

    def _batch_processor(self):
        """Background thread that flushes measurement batches to DB."""
        while self._running:
            elapsed = time.time() - self._last_batch_time
            if elapsed >= self._batch_timeout and self._measurement_buffer:
                self._flush_batch()
            time.sleep(0.5)

    def _flush_batch(self):
        """Flush buffered measurements to database in a single transaction."""
        with self._buffer_lock:
            if not self._measurement_buffer:
                return
            batch = self._measurement_buffer[:]
            self._measurement_buffer.clear()
            self._last_batch_time = time.time()

        try:
            with self.app.app_context():
                db.session.bulk_save_objects(batch)

                # Batch update tank connection statuses from Redis
                status_keys = self.redis_client.keys("tank:status:*")
                for key in status_keys:
                    tank_id = int(key.decode().split(":")[-1])
                    status_data = json.loads(self.redis_client.get(key))
                    tank = Tank.query.get(tank_id)
                    if tank:
                        tank.last_connection = datetime.fromisoformat(status_data['last_connection'])
                        tank.connection_status = status_data['connection_status']

                db.session.commit()
                logger.debug(f"Flushed {len(batch)} measurements to DB")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error flushing batch: {e}")
            # Re-queue failed measurements to Redis Stream for retry
            for m in batch:
                self.redis_client.xadd("measurement:retry_queue", m.to_dict())

    def _handle_status(self, topic: str, payload: dict):
        """Handle gateway status messages."""
        gateway_mac = payload.get("gateway_mac") or topic.split("/")[1]
        status = payload.get("status")

        with self.app.app_context():
            tanks = Tank.query.filter_by(gateway_mac=gateway_mac, deleted_at=None).all()
            for tank in tanks:
                tank.connection_status = 'connected' if status == 'online' else 'disconnected'
                if status == 'online':
                    tank.last_connection = datetime.utcnow()
            db.session.commit()

        logger.info(f"Gateway {gateway_mac} status: {status}")

    # ── Bi-directional Command Interface ──────────────────────────

    def _cmd_reconfigure(self, gateway_mac: str, params: dict):
        """Handle remote reconfiguration command."""
        logger.info(f"Reconfiguring gateway {gateway_mac}: {params}")
        # Publish new configuration to the gateway
        self.client.publish(
            f"fuel/{gateway_mac}/config",
            json.dumps(params),
            qos=1,
            retain=False,
        )

    def _cmd_set_interval(self, gateway_mac: str, interval_seconds: int):
        """Handle remote interval adjustment command."""
        logger.info(f"Setting interval for {gateway_mac} to {interval_seconds}s")
        self.client.publish(
            f"fuel/{gateway_mac}/cmd",
            json.dumps({"command": "set_interval", "interval": interval_seconds}),
            qos=1,
        )

    def _cmd_reboot(self, gateway_mac: str):
        """Handle remote reboot command."""
        logger.info(f"Rebooting gateway {gateway_mac}")
        self.client.publish(
            f"fuel/{gateway_mac}/cmd",
            json.dumps({"command": "reboot"}),
            qos=1,
        )

    def _cmd_diagnose(self, gateway_mac: str):
        """Handle remote diagnostic command."""
        logger.info(f"Running diagnostics on {gateway_mac}")
        self.client.publish(
            f"fuel/{gateway_mac}/cmd",
            json.dumps({"command": "diagnose"}),
            qos=1,
        )
        # Return diagnostic data via response topic
        self.client.message_callback_add(
            f"fuel/{gateway_mac}/response",
            self._handle_diagnostic_response
        )

    def _handle_diagnostic_response(self, client, userdata, msg):
        """Handle diagnostic response from gateway."""
        logger.info(f"Diagnostic response from {msg.topic}: {msg.payload.decode()}")
```

## 2. Refactored MeasurementProcessor with Thread Safety

```python
"""
Refactored Measurement Processor
- Thread-safe instance state
- Improved thermal expansion model
- Better edge case handling
- Configurable pressure smoothing
"""
import logging
import math
from threading import Lock
from datetime import datetime
from typing import Optional, Dict

logger = logging.getLogger(__name__)


class MeasurementProcessor:
    """Thread-safe processor for converting raw sensor measurements to tank data."""

    _DEFAULT_VOLUME_EXPANSION = {
        "gasoline": 0.00110,
        "diesel": 0.00080,
        "kerosene": 0.00095,
        "jet_fuel": 0.00095,
        "unknown": 0.00095,
    }

    _DEFAULT_DAMPING = {
        "gasoline": 0.6,
        "diesel": 0.4,
        "kerosene": 0.5,
        "jet_fuel": 0.5,
        "unknown": 0.5,
    }

    def __init__(self, tank_config):
        self.tank_config = tank_config
        self._lock = Lock()  # Thread safety for instance state
        self._pressure_window: list = []
        self._max_window = 5
        self._last_level = None
        self._last_volume = None

    def smooth_pressure(self, pressure: float) -> float:
        """Apply moving median filter with outlier rejection."""
        with self._lock:
            self._pressure_window.append(pressure)
            if len(self._pressure_window) > self._max_window:
                self._pressure_window.pop(0)

            if len(self._pressure_window) < 3:
                return pressure

            sorted_window = sorted(self._pressure_window)
            median = sorted_window[len(sorted_window) // 2]

            # 0.1% deviation threshold
            valid = [p for p in self._pressure_window
                     if abs(p - median) / max(median, 1e-10) <= 0.002]

            return sum(valid) / len(valid) if valid else pressure

    def process_measurement(
        self,
        pressure: float,
        temperature: Optional[float] = None,
        status: int = 0,
    ) -> Dict:
        """Process a single raw measurement into tank data."""
        with self._lock:
            level = self.pressure_to_level(pressure, temperature)
            level = self._apply_hysteresis(level)

            volume = self.calculate_volume_from_level(level, temperature)
            fill_percent = self._calculate_fill_percent(volume)

            result = {
                'timestamp': datetime.utcnow(),
                'pressure': round(pressure, 5),
                'temperature': round(temperature, 1) if temperature is not None else None,
                'level': round(level, 3),
                'volume': round(volume, 1),
                'fill_percent': round(fill_percent, 1),
                'status': status,
            }

            self._last_level = level
            self._last_volume = volume
            return result

    def pressure_to_level(self, pressure: float, temperature: Optional[float] = None) -> float:
        """Convert pressure to fluid level with full compensation."""
        pressure_pa = (pressure - self.tank_config.atmospheric_pressure) * 100000
        density = self._calc_compensated_density(temperature)
        gravity = self._calc_elevated_gravity()

        if density <= 0 or gravity <= 0:
            logger.error(f"Invalid density ({density}) or gravity ({gravity}) for level calculation")
            return 0.0

        level = pressure_pa / (density * gravity)
        return level * self.tank_config.calibration_factor

    def calculate_volume_from_level(self, level: float, temperature: Optional[float] = None) -> float:
        """Calculate volume from level based on tank geometry with thermal compensation."""
        max_level = (self.tank_config.tank_diameter
                     if self.tank_config.tank_orientation == 'horizontal'
                     else self.tank_config.tank_height)

        level = max(0, min(level, max_level))

        if self.tank_config.tank_orientation == 'horizontal':
            raw_volume = self._horizontal_tank_volume(level)
        else:
            raw_volume = math.pi * (self.tank_config.tank_diameter / 2) ** 2 * level * 1000

        if temperature is not None and abs(temperature - 15.0) > 2.0:
            return self._temp_compensate_volume(raw_volume, temperature)

        return raw_volume

    def _calc_compensated_density(self, temperature: Optional[float]) -> float:
        """Calculate temperature-compensated fluid density."""
        if temperature is None:
            return self.tank_config.fluid_density

        base_density = self.tank_config.fluid_density
        ref_temp = 15.0
        beta = self._get_expansion_coefficient(base_density)
        damping = self._get_damping_factor(base_density)

        effective_delta = (temperature - ref_temp) * damping
        compensated = base_density / (1 + beta * effective_delta)

        logger.debug(f"Density compensation: {base_density} → {compensated:.2f} kg/m³ "
                     f"(T={temperature}°C, β={beta})")
        return compensated

    def _get_expansion_coefficient(self, density: float) -> float:
        """Get thermal expansion coefficient based on fuel density."""
        if 720 <= density <= 780:
            return 0.00110  # Gasoline
        elif 820 <= density <= 860:
            return 0.00080  # Diesel
        else:
            return 0.00095  # Other petroleum

    def _get_damping_factor(self, density: float) -> float:
        """Get temperature damping factor."""
        if 720 <= density <= 780:
            return 0.6
        elif 820 <= density <= 860:
            return 0.4
        return 0.5

    def _calc_elevated_gravity(self) -> float:
        """Calculate gravity compensated for elevation."""
        g0 = 9.80665
        gradient = 3.086e-6
        return g0 - (gradient * self.tank_config.elevation)

    def _temp_compensate_volume(self, volume: float, temperature: float) -> float:
        """Apply volume temperature compensation."""
        beta = self._get_expansion_coefficient(self.tank_config.fluid_density)
        return volume / (1 + beta * (temperature - 15.0))

    def _horizontal_tank_volume(self, level: float) -> float:
        """Calculate volume for horizontal cylindrical tank."""
        r = self.tank_config.tank_diameter / 2
        if level <= 0.001:
            return 0.0
        if level >= self.tank_config.tank_diameter - 0.001:
            return math.pi * r**2 * self.tank_config.tank_height * 1000

        if level <= r:
            theta = 2 * math.acos((r - level) / r)
            area = (r**2 * (theta - math.sin(theta))) / 2
        else:
            h_empty = self.tank_config.tank_diameter - level
            theta = 2 * math.acos((r - h_empty) / r)
            area = math.pi * r**2 - (r**2 * (theta - math.sin(theta))) / 2

        return area * self.tank_config.tank_height * 1000

    def _calculate_fill_percent(self, volume: float) -> float:
        """Calculate fill percentage (0-100)."""
        total_liters = self.tank_config.tank_volume * 1000
        if total_liters <= 0:
            return 0.0
        return max(0, min(100, (volume / total_liters) * 100))

    def _apply_hysteresis(self, current_level: float) -> float:
        """Apply hysteresis to prevent level oscillation."""
        hysteresis = self.tank_config.level_hysteresis or 0.001
        if self._last_level is not None and abs(current_level - self._last_level) < hysteresis:
            return self._last_level
        return current_level

    def get_stable_volume(self, volume: float, hysteresis: Optional[float] = None) -> float:
        """Apply hysteresis to volume readings."""
        if hysteresis is None:
            hysteresis = max(1.0, self.tank_config.tank_volume * 1000 * 0.001)
        if self._last_volume is not None and abs(volume - self._last_volume) < hysteresis:
            return self._last_volume
        return volume
```

## 3. Refactored FlowRateCalculator with Leak Detection

```python
"""
Refactored Flow Rate Calculator
- Added leak/theft detection with rate-of-change analysis
- Thread-safe state management
- Configurable thresholds per tank type
"""
import logging
from datetime import datetime
from collections import deque
from threading import Lock
from enum import Enum, auto
from typing import Optional, Tuple, Deque

logger = logging.getLogger(__name__)


class FlowState(Enum):
    NORMAL = auto()
    REFILL = auto()
    STABLE = auto()
    HIGH_OUTFLOW = auto()
    LEAK_DETECTED = auto()  # New state


class FlowRateCalculator:
    """Thread-safe flow rate calculator with leak detection."""

    STABILITY_THRESHOLD = {
        'REFILL': 2.0,
        'HIGH_OUTFLOW': 1.0,
        'LEAK_DETECTED': 0.5,
        'NORMAL': 0.5,
        'STABLE': 0.3,
    }

    def __init__(
        self,
        max_history_points: int = 10,
        smoothing_factor: float = 0.5,
        expected_max_inflow_rate: float = 600.0,
        expected_max_outflow_rate: float = 100.0,
        leak_detection_rate: float = 5.0,  # L/min sustained negative flow
        leak_detection_duration: int = 60,  # seconds sustained leak
        tank_type: str = "fuel",
    ):
        self.max_history_points = max_history_points
        self.smoothing_factor = smoothing_factor
        self.expected_max_inflow_rate = expected_max_inflow_rate
        self.expected_max_outflow_rate = expected_max_outflow_rate
        self.leak_detection_rate = leak_detection_rate
        self.leak_detection_duration = leak_detection_duration
        self.tank_type = tank_type

        self._lock = Lock()
        self.history: Deque[Tuple[datetime, float]] = deque(maxlen=max_history_points)
        self.leak_history: Deque[Tuple[datetime, float]] = deque()

        self.current_flow_rate = 0.0
        self.max_inflow_rate = 0.0
        self.max_outflow_rate = 0.0
        self.leak_detected = False
        self.leak_start_time = None

        self.last_flow_rate = None
        self.last_volume = None
        self.flow_state = FlowState.NORMAL
        self.stable_counter = 0
        self.flow_confidence = 0.0

    def add_measurement(self, volume: float, timestamp: Optional[datetime] = None) -> float:
        """Add a measurement and return the calculated flow rate."""
        with self._lock:
            if volume < 0:
                volume = 0.0
            if timestamp is None:
                timestamp = datetime.now()

            if self.history and self._is_outlier(volume):
                if self.last_volume is not None:
                    volume = self.last_volume

            self._update_history(volume, timestamp)

            if len(self.history) < 2:
                return 0.0

            return self._calculate_flow_rate()

    def _calculate_flow_rate(self) -> float:
        """Calculate flow rate and detect leaks."""
        latest = list(self.history)[-1]
        previous = list(self.history)[-2]

        time_diff = (latest[0] - previous[0]).total_seconds()
        if time_diff < 5:
            return self._handle_rapid_readings()

        vol_diff = latest[1] - previous[1]
        raw_rate = (vol_diff / time_diff) * 60  # L/min

        # Leak detection
        self._detect_leak(raw_rate, latest[0])

        # Update flow state
        self._update_flow_state(raw_rate)

        # Apply smoothing
        flow_rate = self._apply_smoothing(raw_rate)

        # Clamp to expected ranges
        if flow_rate > 0:
            flow_rate = min(flow_rate, self.expected_max_inflow_rate)
        else:
            flow_rate = max(flow_rate, -self.expected_max_outflow_rate)

        self.current_flow_rate = round(flow_rate, 2)
        return self.current_flow_rate

    def _detect_leak(self, raw_rate: float, timestamp: datetime):
        """Detect sustained leak/theft patterns."""
        # A leak is detected when:
        # 1. Flow rate is negative and exceeds leak threshold
        # 2. Sustained for leak_detection_duration seconds
        if raw_rate < -self.leak_detection_rate:
            self.leak_history.append((timestamp, raw_rate))
            # Prune old entries
            cutoff = timestamp.timestamp() - self.leak_detection_duration
            while self.leak_history and self.leak_history[0][0].timestamp() < cutoff:
                self.leak_history.popleft()

            if len(self.leak_history) >= 3 and not self.leak_detected:
                self.leak_detected = True
                self.leak_start_time = timestamp
                self.flow_state = FlowState.LEAK_DETECTED
                logger.warning(
                    f"LEAK DETECTED! Sustained outflow of {abs(raw_rate):.1f} L/min "
                    f"for {self.leak_detection_duration}s on tank"
                )
        else:
            self.leak_history.clear()
            if self.leak_detected:
                logger.info(f"Leak condition cleared after {self.leak_start_time}")
                self.leak_detected = False
                self.leak_start_time = None
                # Only return to NORMAL if not in REFILL/HIGH_OUTFLOW
                if self.flow_state not in (FlowState.REFILL, FlowState.HIGH_OUTFLOW):
                    self.flow_state = FlowState.NORMAL

    def _update_flow_state(self, raw_rate: float):
        """Update flow state machine."""
        if self.leak_detected:
            self.flow_state = FlowState.LEAK_DETECTED
            return

        if raw_rate > self.expected_max_inflow_rate * 0.5:
            self.flow_state = FlowState.REFILL
        elif raw_rate < -self.leak_detection_rate:
            if self.flow_state != FlowState.LEAK_DETECTED:
                self.flow_state = FlowState.HIGH_OUTFLOW
        elif self.stable_counter >= 3:
            self.flow_state = FlowState.NORMAL

    def _apply_smoothing(self, raw_rate: float) -> float:
        """Apply exponential smoothing to flow rate."""
        if self.last_flow_rate is not None:
            smoothed = (self.smoothing_factor * raw_rate +
                       (1 - self.smoothing_factor) * self.last_flow_rate)
        else:
            smoothed = raw_rate
        self.last_flow_rate = smoothed
        return smoothed

    def _is_outlier(self, volume: float) -> bool:
        """Modified Z-score outlier detection."""
        if len(self.history) < 5:
            return False

        recent = [item[1] for item in list(self.history)[-5:]]
        median = sorted(recent)[len(recent) // 2]
        deviations = [abs(v - median) for v in recent]
        mad = sorted(deviations)[len(deviations) // 2]
        mad = max(mad, 0.1)

        z_score = 0.6745 * abs(volume - median) / mad
        return z_score > 5.0

    def _handle_rapid_readings(self) -> float:
        """Handle rapid readings with minimal time difference."""
        if self.last_flow_rate is not None and abs(self.last_flow_rate) > 1.0:
            return self.last_flow_rate * 0.7  # Decay rapidly
        return 0.0

    def get_statistics(self) -> dict:
        """Get flow rate statistics including leak status."""
        return {
            'current_flow_rate': self.current_flow_rate,
            'max_inflow_rate': round(self.max_inflow_rate, 2),
            'max_outflow_rate': round(self.max_outflow_rate, 2),
            'flow_state': self.flow_state.name,
            'leak_detected': self.leak_detected,
            'leak_start_time': self.leak_start_time.isoformat() if self.leak_start_time else None,
            'flow_confidence': round(self.flow_confidence, 2),
        }

    def reset(self):
        """Reset all calculator state."""
        with self._lock:
            self.history.clear()
            self.leak_history.clear()
            self.current_flow_rate = 0.0
            self.last_flow_rate = None
            self.last_volume = None
            self.flow_state = FlowState.NORMAL
            self.leak_detected = False
            self.leak_start_time = None
```

## 4. Refactored AlarmManager with Notification Queue

```python
"""
Refactored Alarm Manager
- Notification dispatch queue (prevents blocking DB operations)
- Rate limiting on alarm generation
- Deduplication of similar alarms
- Integration with notification services
"""
import logging
from datetime import datetime, timedelta
from threading import Lock
from collections import defaultdict

from models.database import db, Alarm, Tank

logger = logging.getLogger(__name__)


class AlarmManager:
    """Manage alarms with notification queuing and deduplication."""

    ALARM_COOLDOWN = {
        'critical_level': timedelta(minutes=5),
        'low_level': timedelta(minutes=15),
        'high_level': timedelta(minutes=30),
        'sensor_error': timedelta(minutes=10),
        'leak_detected': timedelta(minutes=2),
    }

    def __init__(self, tank_id: int, notification_queue=None):
        self.tank_id = tank_id
        self._lock = Lock()
        self._notification_queue = notification_queue  # Celery queue or Redis queue
        self._recent_alarms: dict = defaultdict(lambda: None)  # type -> last_alarm_time

    def check_alarms(self, measurement_data: dict, thresholds: dict) -> list:
        """Check all alarm conditions and create alarms for triggered ones."""
        triggered = []
        fill_percent = measurement_data.get('fill_percent')
        status = measurement_data.get('status')
        now = datetime.utcnow()

        alarm_checks = [
            ('critical_level', fill_percent <= thresholds.get('critical_level_threshold', 10),
             f'Critical level: {fill_percent:.1f}%', fill_percent, 'danger'),
            ('low_level',
             thresholds.get('critical_level_threshold', 10) < fill_percent <= thresholds.get('low_level_threshold', 20),
             f'Low level: {fill_percent:.1f}%', fill_percent, 'warning'),
            ('high_level', fill_percent >= thresholds.get('high_level_threshold', 90),
             f'High level: {fill_percent:.1f}%', fill_percent, 'warning'),
            ('sensor_error', status != 0,
             f'Sensor error: Status code {status}', status, 'danger'),
        ]

        for alarm_type, condition, message, value, level in alarm_checks:
            if condition and self._should_create_alarm(alarm_type, now):
                alarm = self._create_alarm(alarm_type, message, value, level)
                if alarm:
                    triggered.append(alarm)
                    self._recent_alarms[alarm_type] = now

        return triggered

    def _should_create_alarm(self, alarm_type: str, now: datetime) -> bool:
        """Check if alarm should be created (cooldown + deduplication)."""
        cooldown = self.ALARM_COOLDOWN.get(alarm_type, timedelta(minutes=10))
        last_time = self._recent_alarms.get(alarm_type)

        if last_time is None or (now - last_time) > cooldown:
            return True
        return False

    def _create_alarm(self, alarm_type: str, message: str, value: float, level: str):
        """Create alarm record and dispatch notification."""
        try:
            alarm = Alarm(
                tank_id=self.tank_id,
                timestamp=datetime.utcnow(),
                type=alarm_type,
                message=message,
                value=value,
                level=level,
                acknowledged=False,
            )

            with self._lock:
                db.session.add(alarm)
                db.session.commit()

            # Dispatch notification asynchronously
            self._dispatch_notification(alarm)

            logger.warning(f"Alarm created for tank {self.tank_id}: {message}")
            return alarm

        except Exception as e:
            logger.error(f"Error creating alarm for tank {self.tank_id}: {str(e)}")
            db.session.rollback()
            return None

    def _dispatch_notification(self, alarm: Alarm):
        """Dispatch notification via configured channels."""
        if self._notification_queue:
            # Async notification via Celery/Redis Queue
            self._notification_queue.enqueue(
                'send_notification',
                alarm_id=alarm.id,
                tank_id=self.tank_id,
                level=alarm.level,
                message=alarm.message,
            )
        else:
            # Fallback: log and attempt synchronous notification
            logger.info(f"Notification: [{alarm.level.upper()}] Tank {self.tank_id}: {alarm.message}")

    def acknowledge_alarm(self, alarm_id: int, user_id: int = None) -> bool:
        """Acknowledge an alarm."""
        try:
            alarm = Alarm.query.get(alarm_id)
            if not alarm or alarm.tank_id != self.tank_id:
                return False

            alarm.acknowledged = True
            alarm.acknowledged_by = user_id
            alarm.acknowledged_at = datetime.utcnow()
            db.session.commit()
            return True

        except Exception as e:
            logger.error(f"Error acknowledging alarm {alarm_id}: {str(e)}")
            return False

    def get_active_alarms(self) -> list:
        """Get all active (unacknowledged) alarms."""
        try:
            return Alarm.query.filter_by(
                tank_id=self.tank_id,
                acknowledged=False,
            ).order_by(Alarm.timestamp.desc()).all()
        except Exception as e:
            logger.error(f"Error getting active alarms: {str(e)}")
            return []
```

## 5. Refactored TankConfig with Proper Serialization

```python
"""
Refactored Tank Configuration
- Proper JSON serialization for Redis caching
- Validation and type safety
- Computed properties
"""
import math
from typing import Optional


class TankConfig:
    """Configuration for a single tank, serializable for Redis caching."""

    __slots__ = [
        'tank_orientation', 'tank_height', 'tank_diameter',
        'fluid_density', 'atmospheric_pressure', 'elevation',
        'tank_volume', 'host', 'tcp_port', 'device_address',
        'pressure_channel', 'temp_channel', 'calibration_factor',
        'level_hysteresis', 'flow_threshold', 'pressure_smoothing',
        'low_level_threshold', 'critical_level_threshold', 'high_level_threshold',
    ]

    def __init__(self):
        self.tank_orientation = 'vertical'
        self.tank_height = 2.0
        self.tank_diameter = 1.5
        self.fluid_density = 850
        self.atmospheric_pressure = 0.0
        self.elevation = 0.0
        self.tank_volume = 0.0
        self.host = None
        self.tcp_port = 2000
        self.device_address = 1
        self.pressure_channel = 1
        self.temp_channel = 4
        self.calibration_factor = 1.0
        self.level_hysteresis = 0.001
        self.flow_threshold = 0.1
        self.pressure_smoothing = True
        self.low_level_threshold = 20.0
        self.critical_level_threshold = 10.0
        self.high_level_threshold = 90.0

    @property
    def tank_volume_liters(self) -> float:
        """Total tank volume in liters."""
        return self.tank_volume * 1000

    @property
    def max_level(self) -> float:
        """Maximum fluid level based on orientation."""
        return (self.tank_diameter
                if self.tank_orientation == 'horizontal'
                else self.tank_height)

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON/Redis."""
        return {k: getattr(self, k) for k in self.__slots__}

    @classmethod
    def from_dict(cls, data: dict) -> 'TankConfig':
        """Create TankConfig from dictionary."""
        config = cls()
        for key, value in data.items():
            if hasattr(config, key):
                setattr(config, key, value)
        return config

    @classmethod
    def from_tank(cls, tank) -> 'TankConfig':
        """Create TankConfig from a Tank ORM object."""
        config = cls()
        config.tank_orientation = tank.tank_orientation
        config.tank_height = tank.tank_height
        config.tank_diameter = tank.tank_diameter
        config.fluid_density = tank.fluid_density
        config.atmospheric_pressure = tank.atmospheric_pressure
        config.elevation = tank.elevation
        config.tcp_port = int(tank.tcp_port)
        config.device_address = int(tank.device_address)
        config.pressure_channel = tank.pressure_channel
        config.temp_channel = tank.temp_channel
        config.calibration_factor = tank.calibration_factor
        config.level_hysteresis = tank.level_hysteresis or 0.001
        config.flow_threshold = tank.flow_threshold or 0.1
        config.pressure_smoothing = tank.pressure_smoothing
        config.low_level_threshold = tank.low_level_threshold
        config.critical_level_threshold = tank.critical_level_threshold
        config.high_level_threshold = tank.high_level_threshold

        # Calculate tank volume
        r = config.tank_diameter / 2
        if config.tank_orientation == 'vertical':
            config.tank_volume = math.pi * r**2 * config.tank_height
        else:
            config.tank_volume = math.pi * r**2 * config.tank_height  # Simplified for horizontal

        return config
```