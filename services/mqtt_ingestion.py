"""
MQTT Ingestion Service for Fuel Monitoring

Receives raw sensor readings from ESP32-S3 gateways via MQTT,
looks up the tank by gateway MAC + sensor serial number,
runs the existing MeasurementProcessor pipeline,
and saves measurements to TimescaleDB.
"""
import json
import logging
import threading
import time
from datetime import datetime
from flask import Flask

import paho.mqtt.client as mqtt

from models.database import db, Tank, Measurement
from models.measurement_processor import MeasurementProcessor
from models.flow_rate_calculator import FlowRateCalculator
from models.alarm_manager import AlarmManager
from models.tank_config import TankConfig

logger = logging.getLogger("MqttIngestion")

class MqttIngestionService:
    """
    MQTT client that ingests raw sensor data from ESP32 gateways
    and feeds it into the existing cloud processing pipeline.
    """
    
    def __init__(self, app: Flask, broker: str, port: int = 1883,
                 username: str = None, password: str = None):
        self.app = app
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password
        
        # Topic patterns
        self.topic_readings = "fuel/+/readings"      # fuel/{gateway_mac}/readings
        self.topic_status = "fuel/+/status"          # fuel/{gateway_mac}/status
        
        self.client = mqtt.Client()
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        
        if username and password:
            self.client.username_pw_set(username, password)
        
        # Set Last Will for the service itself (not for gateways)
        self.client.will_set("fuel/service/status", 
                            json.dumps({"status": "offline"}), 
                            retain=True)
        
        self._running = False
        self._thread = None
        
        # Cache: gateway_mac -> list of tanks (to avoid DB lookups every message)
        self._tank_cache = {}
        self._cache_lock = threading.Lock()
        self._cache_ttl = 300  # 5 minutes
    
    def start(self):
        """Start the MQTT ingestion service in a background thread."""
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("MQTT Ingestion Service started")
    
    def stop(self):
        """Stop the service gracefully."""
        self._running = False
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
                time.sleep(10)
    
    def _on_connect(self, client, userdata, flags, rc):
        """Subscribe to all gateway topics on connect."""
        if rc == 0:
            logger.info(f"Connected to MQTT broker: {self.broker}")
            client.subscribe(self.topic_readings)
            client.subscribe(self.topic_status)
            client.publish("fuel/service/status", 
                          json.dumps({"status": "online", "timestamp": time.time()}),
                          retain=True)
        else:
            logger.error(f"MQTT connection failed with code: {rc}")
    
    def _on_disconnect(self, client, userdata, rc):
        logger.warning(f"MQTT disconnected with code: {rc}")
    
    def _on_message(self, client, userdata, msg):
        """Route incoming MQTT messages."""
        try:
            topic = msg.topic
            payload = json.loads(msg.payload.decode('utf-8'))
            
            if "/readings" in topic:
                self._handle_reading(topic, payload)
            elif "/status" in topic:
                self._handle_status(topic, payload)
                
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in MQTT message: {e}")
        except Exception as e:
            logger.error(f"Error processing MQTT message: {e}")
    
    def _handle_reading(self, topic: str, payload: dict):
        """
        Process a raw sensor reading from an ESP32 gateway.
        
        Expected payload:
        {
            "gateway_mac": "aabbcc112233",
            "site_id": "site_001",
            "timestamp": 1693948800,
            "sensors": [
                {
                    "serial_number": 12345678,
                    "device_address": 1,
                    "pressure_bar": 1.2450,
                    "temperature_c": 23.5,
                    "status": 0,
                    "timestamp": 1693948800
                }
            ]
        }
        """
        gateway_mac = payload.get("gateway_mac") or topic.split("/")[1]
        sensors = payload.get("sensors", [])
        
        for sensor_data in sensors:
            self._process_sensor(gateway_mac, sensor_data)
    
    def _process_sensor(self, gateway_mac: str, sensor_data: dict):
        """Process a single sensor's raw data through the cloud pipeline."""
        serial_number = sensor_data.get("serial_number")
        device_address = sensor_data.get("device_address")
        pressure = sensor_data.get("pressure_bar")
        temperature = sensor_data.get("temperature_c")
        status = sensor_data.get("status", 0)
        timestamp = sensor_data.get("timestamp")
        
        if pressure is None:
            return
        
        # Look up tank (by SN first, then by MAC + address)
        tank = self._find_tank(gateway_mac, serial_number, device_address)
        if not tank:
            logger.warning(f"No tank found for GW:{gateway_mac} SN:{serial_number} ADDR:{device_address}")
            return
        
        # Process within Flask app context
        with self.app.app_context():
            try:
                # 1. Build tank config (reuses your existing logic)
                config = TankConfig.from_database(tank, self.app.config)
                
                # 2. Process measurement (pressure → level → volume → fill %)
                processor = MeasurementProcessor(config)
                measurement_data = processor.process_measurement(pressure, temperature, status)
                
                # 3. Calculate flow rate (reuses your existing FlowRateCalculator)
                # We need the previous measurement for flow calculation
                latest = Measurement.query.filter_by(tank_id=tank.id)\
                    .order_by(Measurement.timestamp.desc()).first()
                
                flow_rate = 0.0
                if latest and 'volume' in measurement_data:
                    # Simple flow calculation - you can integrate your full FlowRateCalculator here
                    time_diff = (datetime.fromtimestamp(timestamp) - latest.timestamp).total_seconds()
                    if time_diff > 0:
                        vol_diff = measurement_data['volume'] - latest.volume
                        flow_rate = (vol_diff / time_diff) * 60  # L/min
                
                measurement_data['flow_rate'] = flow_rate
                
                # 4. Save to database
                measurement = Measurement(
                    tank_id=tank.id,
                    timestamp=datetime.fromtimestamp(timestamp),
                    pressure=measurement_data['pressure'],
                    temperature=measurement_data['temperature'],
                    level=measurement_data['level'],
                    volume=measurement_data['volume'],
                    flow_rate=measurement_data['flow_rate'],
                    fill_percent=measurement_data['fill_percent'],
                    status=measurement_data['status']
                )
                
                # Update tank connection status
                tank.last_connection = datetime.now()
                tank.connection_status = 'connected'
                
                db.session.add(measurement)
                db.session.commit()
                
                # 5. Check alarms (reuses your existing AlarmManager)
                alarm_mgr = AlarmManager(tank.id, db.session, app=self.app)
                alarm_mgr.check_alarms(measurement_data, {
                    'low_level_threshold': tank.low_level_threshold,
                    'critical_level_threshold': tank.critical_level_threshold,
                    'high_level_threshold': tank.high_level_threshold
                })
                
                logger.debug(f"Saved measurement for tank {tank.name} (SN:{serial_number})")
                
            except Exception as e:
                db.session.rollback()
                logger.error(f"Error processing sensor SN:{serial_number}: {e}")
    
    def _find_tank(self, gateway_mac: str, serial_number: int, device_address: int):
        """
        Find tank by sensor serial number (preferred) or gateway MAC + device address.
        Uses an in-memory cache to reduce DB load.
        """
        cache_key = f"{serial_number}" if serial_number else f"{gateway_mac}:{device_address}"
        
        with self._cache_lock:
            cached = self._tank_cache.get(cache_key)
            if cached and (time.time() - cached['time']) < self._cache_ttl:
                return cached['tank']
        
        with self.app.app_context():
            # Priority 1: Find by sensor serial number (most reliable)
            if serial_number:
                tank = Tank.query.filter_by(
                    sensor_serial_number=serial_number,
                    deleted_at=None
                ).first()
                if tank:
                    self._cache_tank(cache_key, tank)
                    return tank
            
            # Priority 2: Find by gateway MAC + RS485 address
            tank = Tank.query.filter_by(
                gateway_mac=gateway_mac,
                device_address=device_address,
                deleted_at=None
            ).first()
            
            if tank:
                # If we found by MAC+address but SN was provided, update the tank's SN
                if serial_number and not tank.sensor_serial_number:
                    tank.sensor_serial_number = serial_number
                    db.session.commit()
                    logger.info(f"Auto-registered SN:{serial_number} for tank {tank.name}")
                
                self._cache_tank(cache_key, tank)
                return tank
        
        return None
    
    def _cache_tank(self, key: str, tank):
        with self._cache_lock:
            self._tank_cache[key] = {
                'tank': tank,
                'time': time.time()
            }
    
    def _handle_status(self, topic: str, payload: dict):
        """Handle gateway status messages (online/offline)."""
        gateway_mac = payload.get("gateway_mac") or topic.split("/")[1]
        status = payload.get("status")
        
        with self.app.app_context():
            tanks = Tank.query.filter_by(gateway_mac=gateway_mac, deleted_at=None).all()
            for tank in tanks:
                tank.connection_status = 'connected' if status == 'online' else 'disconnected'
                if status == 'online':
                    tank.last_connection = datetime.now()
            db.session.commit()
        
        logger.info(f"Gateway {gateway_mac} status: {status}")