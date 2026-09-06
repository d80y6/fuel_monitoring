"""
MQTT Ingestion Service for Fuel Monitoring

Receives raw sensor readings from ESP32-S3 gateways via MQTT,
validates payloads against JSON schema, looks up tanks via Redis-backed
LRU cache, processes measurements through the full pipeline, and
batches DB writes for performance.
"""
import json
import logging
import threading
import time
import uuid
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional

import paho.mqtt.client as mqtt
from jsonschema import validate, ValidationError

from models.database import db, Tank, Measurement
from models.measurement_processor import MeasurementProcessor
from models.flow_rate_calculator import FlowRateCalculator
from models.alarm_manager import AlarmManager
from models.tank_config import TankConfig

logger = logging.getLogger("MqttIngestion")

# JSON schema for incoming sensor readings
READING_SCHEMA = {
    "type": "object",
    "required": ["gateway_mac", "sensors"],
    "properties": {
        "gateway_mac": {"type": "string", "pattern": "^[a-fA-F0-9]{12}$"},
        "site_id": {"type": "string"},
        "timestamp": {"type": ["integer", "number"]},
        "sensors": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["serial_number", "pressure_bar"],
                "properties": {
                    "serial_number": {"type": "integer"},
                    "device_address": {"type": "integer"},
                    "pressure_bar": {"type": "number"},
                    "temperature_c": {"type": ["number", "null"]},
                    "status": {"type": "integer"},
                    "timestamp": {"type": ["integer", "number"]},
                },
            },
        },
    },
    "additionalProperties": False,
}

STATUS_SCHEMA = {
    "type": "object",
    "required": ["gateway_mac", "status"],
    "properties": {
        "gateway_mac": {"type": "string", "pattern": "^[a-fA-F0-9]{12}$"},
        "status": {"type": "string", "enum": ["online", "offline"]},
    },
    "additionalProperties": False,
}


class _RedisLRUCache:
    """Redis-backed LRU cache for tank lookups.

    Falls back to an in-memory dict when Redis is unavailable.
    Keys are prefixed with ``tank_lookup:`` in Redis.
    """

    REDIS_PREFIX = "tank_lookup:"
    MAX_REDIS_KEYS = 10_000

    def __init__(self, redis_client=None, default_ttl: int = 300):
        self._redis = redis_client
        self._default_ttl = default_ttl
        self._fallback: Dict[str, dict] = {}
        self._lock = threading.Lock()
        self._redis_available = redis_client is not None

    def get(self, key: str) -> Optional[Any]:
        if self._redis_available:
            try:
                raw = self._redis.get(f"{self.REDIS_PREFIX}{key}")
                if raw is not None:
                    return json.loads(raw)
                return None
            except Exception as exc:
                logger.warning("Redis get failed for %s: %s", key, exc)
                self._redis_available = False
        with self._lock:
            entry = self._fallback.get(key)
            if entry and time.time() < entry["expires"]:
                return entry["value"]
            if entry:
                del self._fallback[key]
            return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        ttl = ttl or self._default_ttl
        if self._redis_available:
            try:
                serialized = json.dumps(value, default=str)
                pipe = self._redis.pipeline()
                pipe.setex(f"{self.REDIS_PREFIX}{key}", ttl, serialized)
                pipe.zadd(
                    f"{self.REDIS_PREFIX}meta",
                    {key: time.time()},
                )
                count = self._redis.zcard(f"{self.REDIS_PREFIX}meta")
                if count > self.MAX_REDIS_KEYS:
                    oldest = self._redis.zrange(
                        f"{self.REDIS_PREFIX}meta", 0, count - self.MAX_REDIS_KEYS
                    )
                    if oldest:
                        pipe.zrem(f"{self.REDIS_PREFIX}meta", *oldest)
                        for k in oldest:
                            pipe.delete(f"{self.REDIS_PREFIX}{k.decode()}")
                pipe.execute()
                return
            except Exception as exc:
                logger.warning("Redis set failed for %s: %s", key, exc)
                self._redis_available = False
        with self._lock:
            if len(self._fallback) >= self.MAX_REDIS_KEYS:
                oldest_key = min(
                    self._fallback, key=lambda k: self._fallback[k]["created"]
                )
                del self._fallback[oldest_key]
            self._fallback[key] = {
                "value": value,
                "created": time.time(),
                "expires": time.time() + ttl,
            }

    def invalidate(self, key: str):
        if self._redis_available:
            try:
                self._redis.delete(f"{self.REDIS_PREFIX}{key}")
                self._redis.zrem(f"{self.REDIS_PREFIX}meta", key)
            except Exception:
                pass
        with self._lock:
            self._fallback.pop(key, None)


class MqttIngestionService:
    """
    MQTT client that ingests raw sensor data from ESP32 gateways
    and feeds it into the cloud processing pipeline.
    """

    def __init__(
        self,
        app,
        broker: str,
        port: int = 1883,
        username: str = None,
        password: str = None,
        ca_cert: str = None,
        client_cert: str = None,
        client_key: str = None,
        sse_broker=None,
    ):
        self.app = app
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password
        self._sse_broker = sse_broker

        # TLS
        self._ca_cert = ca_cert or app.config.get("MQTT_CA_CERT")
        self._client_cert = client_cert or app.config.get("MQTT_CLIENT_CERT")
        self._client_key = client_key or app.config.get("MQTT_CLIENT_KEY")

        # Topic patterns
        self.topic_readings = "fuel/+/readings"
        self.topic_status = "fuel/+/status"

        # Flow rate calculators keyed by tank_id
        self._flow_calculators: Dict[int, FlowRateCalculator] = {}
        self._flow_calc_lock = threading.Lock()

        # Measurement processor cache keyed by tank_id
        self._processors: Dict[int, MeasurementProcessor] = {}

        # Batch buffer for DB writes
        self._batch_buffer: List[Measurement] = []
        self._batch_lock = threading.Lock()
        self._batch_size = 50
        self._batch_interval = 5.0  # seconds
        self._last_flush = time.time()
        self._flush_timer: Optional[threading.Timer] = None

        # Reconnection backoff
        self._reconnect_delay = 1.0
        self._reconnect_max_delay = 120.0
        self._reconnect_attempt = 0

        # Redis-backed tank lookup cache
        self._tank_cache = _RedisLRUCache(
            redis_client=self._get_redis_client(), default_ttl=300
        )

        # MQTT client
        self.client = mqtt.Client(
            client_id=f"fuel_ingestion_{uuid.uuid4().hex[:8]}"
        )
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

        if username and password:
            self.client.username_pw_set(username, password)

        # TLS
        if self._ca_cert:
            self.client.tls_set(
                ca_certs=self._ca_cert,
                certfile=self._client_cert,
                keyfile=self._client_key,
            )

        # Last Will for this service
        self.client.will_set(
            "fuel/service/status",
            json.dumps({"status": "offline"}),
            retain=True,
        )

        self._running = False
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Redis helper
    # ------------------------------------------------------------------
    def _get_redis_client(self):
        """Return a Redis client or None."""
        try:
            import redis as _redis

            return _redis.Redis.from_url(
                self.app.config.get("REDIS_URL", "redis://localhost:6379/0"),
                decode_responses=False,
                socket_connect_timeout=3,
            )
        except Exception as exc:
            logger.warning("Redis unavailable for tank cache: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("MQTT Ingestion Service started")

    def stop(self):
        self._running = False
        self._flush_batch()
        if self._flush_timer:
            self._flush_timer.cancel()
        if self.client.is_connected():
            self.client.disconnect()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("MQTT Ingestion Service stopped")

    # ------------------------------------------------------------------
    # MQTT loop with exponential backoff
    # ------------------------------------------------------------------
    def _run(self):
        while self._running:
            try:
                self.client.connect(self.broker, self.port, keepalive=60)
                self._reconnect_attempt = 0
                self._reconnect_delay = 1.0
                self.client.loop_forever(retry_first_connection=True)
            except Exception as exc:
                self._reconnect_attempt += 1
                delay = min(
                    self._reconnect_delay * (2 ** (self._reconnect_attempt - 1)),
                    self._reconnect_max_delay,
                )
                logger.error(
                    "MQTT connection error (attempt %d, next in %.1fs): %s",
                    self._reconnect_attempt,
                    delay,
                    exc,
                )
                time.sleep(delay)

    # ------------------------------------------------------------------
    # MQTT callbacks
    # ------------------------------------------------------------------
    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info("Connected to MQTT broker: %s", self.broker)
            client.subscribe(self.topic_readings, qos=1)
            client.subscribe(self.topic_status, qos=1)
            client.publish(
                "fuel/service/status",
                json.dumps({"status": "online", "timestamp": time.time()}),
                retain=True,
            )
        else:
            logger.error("MQTT connection failed with code: %d", rc)

    def _on_disconnect(self, client, userdata, rc):
        logger.warning("MQTT disconnected with code: %d", rc)

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            if "/readings" in msg.topic:
                self._handle_reading(msg.topic, payload)
            elif "/status" in msg.topic:
                self._handle_status(msg.topic, payload)
        except json.JSONDecodeError as exc:
            logger.error("Invalid JSON in MQTT message: %s", exc)
        except Exception as exc:
            logger.error("Error processing MQTT message: %s", exc)

    # ------------------------------------------------------------------
    # Reading handler
    # ------------------------------------------------------------------
    def _handle_reading(self, topic: str, payload: dict):
        try:
            validate(instance=payload, schema=READING_SCHEMA)
        except ValidationError as exc:
            gateway_mac = payload.get("gateway_mac", "unknown")
            error_topic = f"fuel/{gateway_mac}/errors"
            error_response = {
                "error": "validation_failed",
                "message": str(exc.message),
                "timestamp": time.time(),
            }
            self.client.publish(error_topic, json.dumps(error_response))
            logger.warning(
                "Payload validation failed for gateway %s: %s",
                gateway_mac,
                exc.message,
            )
            return

        gateway_mac = payload.get("gateway_mac") or topic.split("/")[1]
        site_id = payload.get("site_id")
        msg_timestamp = payload.get("timestamp", int(time.time()))
        sensors = payload.get("sensors", [])

        for sensor_data in sensors:
            sensor_data.setdefault("timestamp", msg_timestamp)
            self._process_sensor(gateway_mac, site_id, sensor_data)

    def _process_sensor(
        self, gateway_mac: str, site_id: str, sensor_data: dict
    ):
        serial_number = sensor_data.get("serial_number")
        device_address = sensor_data.get("device_address")
        pressure = sensor_data.get("pressure_bar")
        temperature = sensor_data.get("temperature_c")
        status = sensor_data.get("status", 0)
        timestamp = sensor_data.get("timestamp")

        if pressure is None:
            return

        tank = self._find_tank(gateway_mac, serial_number, device_address)
        if not tank:
            logger.warning(
                "No tank found for GW:%s SN:%s ADDR:%s",
                gateway_mac,
                serial_number,
                device_address,
            )
            return

        with self.app.app_context():
            try:
                processor = self._get_processor(tank)
                measurement_data = processor.process_measurement(
                    pressure, temperature, status
                )

                # Flow rate via FlowRateCalculator
                flow_calc = self._get_flow_calculator(tank.id)
                flow_rate = flow_calc.add_measurement(
                    measurement_data["volume"],
                    datetime.fromtimestamp(timestamp),
                )
                measurement_data["flow_rate"] = flow_rate

                measurement = Measurement(
                    tank_id=tank.id,
                    timestamp=datetime.fromtimestamp(timestamp),
                    pressure=measurement_data["pressure"],
                    temperature=measurement_data["temperature"],
                    level=measurement_data["level"],
                    volume=measurement_data["volume"],
                    flow_rate=measurement_data["flow_rate"],
                    fill_percent=measurement_data["fill_percent"],
                    status=measurement_data["status"],
                )

                tank.last_connection = datetime.now()
                tank.connection_status = "connected"

                self._add_to_batch(measurement)

                # Alarm check
                alarm_mgr = AlarmManager(
                    tank.id, db.session, app=self.app
                )
                alarm_mgr.check_alarms(
                    measurement_data,
                    {
                        "low_level_threshold": tank.low_level_threshold,
                        "critical_level_threshold": tank.critical_level_threshold,
                        "high_level_threshold": tank.high_level_threshold,
                    },
                )

                logger.debug(
                    "Buffered measurement for tank %s (SN:%s)",
                    tank.name,
                    serial_number,
                )

            except Exception as exc:
                logger.error(
                    "Error processing sensor SN:%s: %s", serial_number, exc
                )

    def _get_processor(self, tank: Tank) -> MeasurementProcessor:
        if tank.id not in self._processors:
            config = TankConfig.from_database(tank, self.app.config)
            self._processors[tank.id] = MeasurementProcessor(config)
        return self._processors[tank.id]

    def _get_flow_calculator(self, tank_id: int) -> FlowRateCalculator:
        with self._flow_calc_lock:
            if tank_id not in self._flow_calculators:
                self._flow_calculators[tank_id] = FlowRateCalculator(
                    max_history_points=10,
                    tank_type="fuel",
                )
            return self._flow_calculators[tank_id]

    # ------------------------------------------------------------------
    # Batch DB writes
    # ------------------------------------------------------------------
    def _add_to_batch(self, measurement: Measurement):
        with self._batch_lock:
            self._batch_buffer.append(measurement)
            should_flush = len(self._batch_buffer) >= self._batch_size
            if not should_flush and not self._flush_timer:
                self._flush_timer = threading.Timer(
                    self._batch_interval, self._flush_batch
                )
                self._flush_timer.daemon = True
                self._flush_timer.start()
        if should_flush:
            self._flush_batch()

    def _flush_batch(self):
        to_flush: List[Measurement] = []
        with self._batch_lock:
            if not self._batch_buffer:
                return
            to_flush = list(self._batch_buffer)
            self._batch_buffer.clear()
            self._last_flush = time.time()
            if self._flush_timer:
                self._flush_timer.cancel()
                self._flush_timer = None

        with self.app.app_context():
            try:
                db.session.bulk_save_objects(to_flush)
                db.session.commit()
                logger.info("Flushed %d measurements to DB", len(to_flush))
            except Exception as exc:
                db.session.rollback()
                logger.error("Batch flush failed: %s", exc)
                with self._batch_lock:
                    self._batch_buffer = to_flush + self._batch_buffer
                return

        if self._sse_broker:
            for m in to_flush:
                try:
                    self._sse_broker.publish(m.tank_id, {
                        'event': 'measurement',
                        'tank_id': m.tank_id,
                        'timestamp': m.timestamp.isoformat() if m.timestamp else None,
                        'pressure': m.pressure,
                        'temperature': m.temperature,
                        'level': m.level,
                        'volume': m.volume,
                        'flow_rate': m.flow_rate,
                        'fill_percent': m.fill_percent,
                        'status': m.status,
                    })
                except Exception as exc:
                    logger.warning("SSE publish failed for tank %s: %s", m.tank_id, exc)

    # ------------------------------------------------------------------
    # Tank lookup
    # ------------------------------------------------------------------
    def _find_tank(
        self, gateway_mac: str, serial_number: int, device_address: int
    ):
        cache_key = (
            str(serial_number)
            if serial_number
            else f"{gateway_mac}:{device_address}"
        )

        cached = self._tank_cache.get(cache_key)
        if cached is not None:
            if cached == "__NULL__":
                return None
            with self.app.app_context():
                tank = db.session.get(Tank, cached.get("id"))
                if tank and not tank.is_deleted:
                    return tank
                self._tank_cache.invalidate(cache_key)

        with self.app.app_context():
            if serial_number:
                tank = Tank.query.filter_by(
                    sensor_serial_number=serial_number, deleted_at=None
                ).first()
                if tank:
                    self._tank_cache.set(cache_key, {"id": tank.id})
                    return tank

            tank = Tank.query.filter_by(
                gateway_mac=gateway_mac,
                device_address=device_address,
                deleted_at=None,
            ).first()

            if tank:
                if serial_number and not tank.sensor_serial_number:
                    tank.sensor_serial_number = serial_number
                    db.session.commit()
                    logger.info(
                        "Auto-registered SN:%s for tank %s",
                        serial_number,
                        tank.name,
                    )
                self._tank_cache.set(cache_key, {"id": tank.id})
                return tank

        self._tank_cache.set(cache_key, "__NULL__", ttl=60)
        return None

    # ------------------------------------------------------------------
    # Status handler
    # ------------------------------------------------------------------
    def _handle_status(self, topic: str, payload: dict):
        try:
            validate(instance=payload, schema=STATUS_SCHEMA)
        except ValidationError as exc:
            logger.warning("Invalid status payload: %s", exc.message)
            return

        gateway_mac = payload.get("gateway_mac") or topic.split("/")[1]
        status = payload.get("status")

        with self.app.app_context():
            tanks = Tank.query.filter_by(
                gateway_mac=gateway_mac, deleted_at=None
            ).all()
            for tank in tanks:
                tank.connection_status = (
                    "connected" if status == "online" else "disconnected"
                )
                if status == "online":
                    tank.last_connection = datetime.now()
            db.session.commit()

        logger.info("Gateway %s status: %s", gateway_mac, status)

    # ------------------------------------------------------------------
    # Command publishing (bidirectional)
    # ------------------------------------------------------------------
    def publish_command(self, gateway_mac: str, command: dict):
        topic = f"fuel/{gateway_mac}/commands"
        command.setdefault("timestamp", time.time())
        command.setdefault("command_id", uuid.uuid4().hex[:12])
        payload = json.dumps(command)
        info = self.client.publish(topic, payload, qos=1)
        logger.info(
            "Published command to %s: %s", topic, command.get("command")
        )
        return info.rc == mqtt.MQTT_ERR_SUCCESS

    def reconfigure_gateway(self, gateway_mac: str, config: dict):
        return self.publish_command(
            gateway_mac, {"command": "reconfigure", "config": config}
        )

    def set_measurement_interval(self, gateway_mac: str, interval: int):
        return self.publish_command(
            gateway_mac, {"command": "set_interval", "interval": interval}
        )

    def reboot_gateway(self, gateway_mac: str):
        return self.publish_command(gateway_mac, {"command": "reboot"})

    def diagnose_gateway(self, gateway_mac: str):
        return self.publish_command(gateway_mac, {"command": "diagnose"})
