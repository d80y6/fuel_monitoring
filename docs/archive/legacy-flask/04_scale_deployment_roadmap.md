> **ARCHIVE — LEGACY FLASK BUILD (2026-09-06).** This document describes the now-deleted Flask-era codebase (Flask/Jinja templates). It is historical reference only and does **NOT** describe the current system, which is a FastAPI + React platform. Do not treat structure, tests, or claims in this file as current.

# Scale & Deployment Roadmap

## Fuel Monitoring Platform — Scaling to 1000+ Gateways

**Target:** Support 1000+ simultaneous ESP32-S3 gateways, each reporting up to 10 tanks at 5-second intervals.

**Estimated Load:**
- 1000 gateways × 10 tanks × 12 readings/min = **120,000 measurements/hour**
- 2,880,000 measurements/day
- ~100GB/month of raw TimescaleDB data (with compression: ~15GB/month)

---

## Phase 1: Foundation (Weeks 1-2)

### 1.1 Security Hardening

**Priority: CRITICAL — Before any production deployment**

| Task | Details | Effort |
|------|---------|--------|
| Remove hardcoded credentials | Move all secrets to environment variables / Vault | 2h |
| Change default admin password | Force password reset on first login | 1h |
| Enable MQTT TLS | Configure CA cert, client cert, TLS 1.2+ on broker | 4h |
| Add JSON schema validation | Validate all MQTT payloads against schema | 2h |
| Enable HTTPS | Configure SSL certificates on Flask | 2h |

**Files to modify:**
- `app.py`: Remove hardcoded DB URI, add SSL context
- `services/mqtt_ingestion.py`: Add TLS configuration
- `config.py`: Remove defaults, enforce env vars

### 1.2 Redis Infrastructure

**Purpose:** Caching, task queue, rate limiting

| Task | Details |
|------|---------|
| Deploy Redis | Single instance with persistence (AOF) for caching |
| Configure Redis Cache | LRU eviction, TTL-based keys, tank cache |
| Add Redis to requirements.txt | `redis>=5.0.0` |

**Architecture:**
```
                    ┌─────────────┐
                    │   Redis     │
                    │             │
  ┌────────┐ ┌─────┤  Cache      │
  │ MQTT   │────→│  + Queue     │
  │ Service│     │             │
  └────────┘     └──────┬──────┘
                       │
              ┌────────▼────────┐
              │ Celery Workers  │
              │ (2-4 instances) │
              └────────┬────────┘
                       │
              ┌────────▼────────┐
              │  PostgreSQL     │
              │  + TimescaleDB  │
              └─────────────────┘
```

### 1.3 Celery Task Queue

**Purpose:** Offload long-running tasks from Flask workers

```python
# celery_app.py
from celery import Celery
from celery.schedules import crontab

celery_app = Celery('fuel_monitoring', broker='redis://localhost:6379/0')

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_routes={
        'tasks.process_measurements': {'queue': 'ingestion'},
        'tasks.generate_forecasts': {'queue': 'analytics'},
        'tasks.send_notifications': {'queue': 'notifications'},
        'tasks.export_csv': {'queue': 'export'},
    },
    beat_schedule={
        'daily-consumption-report': {
            'task': 'tasks.generate_daily_consumption',
            'schedule': crontab(hour=0, minute=0),
        },
        'cleanup-expired-data': {
            'task': 'tasks.cleanup_old_measurements',
            'schedule': crontab(hour=2, minute=0),
        },
    },
    worker_concurrency=4,
    worker_max_tasks_per_child=1000,  # Prevent memory leaks
    task_acks_late=True,  # Re-queue if worker crashes
    result_expires=3600,
)
```

**Tasks to migrate:**
- `MeasurementProcessor` pipeline
- `AlarmManager` notification dispatch
- `TankForecastService` forecast generation
- CSV export operations
- Daily/weekly/monthly statistics aggregation

---

## Phase 2: Performance Optimization (Weeks 3-4)

### 2.1 Database Optimization

| Task | Details | Impact |
|------|---------|--------|
| Run migration script | Execute `03_database_migration_script.md` | 40% query speedup |
| Configure pgbouncer | Connection pooling at 6432 | Prevent connection exhaustion |
| Add TimescaleDB compression | 7-day compression policy | 80% storage reduction |
| Add continuous aggregate refresh policies | Auto-refresh hourly/daily | Sub-second dashboard queries |
| Optimize connection string | Use pgbouncer instead of direct PG | 3x connection throughput |

### 2.2 Ingestion Pipeline Optimization

**Batch writes:**
```python
# In MqttIngestionService
def _flush_batch(self):
    """Flush buffered measurements to database in a single transaction."""
    with self._buffer_lock:
        batch = self._measurement_buffer[:]
        self._measurement_buffer.clear()

    db.session.bulk_save_objects(batch)  # 100x faster than individual commits
    db.session.commit()
```

**Performance comparison:**
| Method | 1000 measurements | Speedup |
|--------|-------------------|---------|
| Individual `db.session.add()` + commit | ~15 seconds | 1x |
| `bulk_save_objects()` + single commit | ~0.15 seconds | 100x |
| Batch via Celery + COPY command | ~0.05 seconds | 300x |

### 2.3 Edge Firmware Creation (Critical Gap)

**Must create:** `firmware/` directory with MicroPython code for ESP32-S3

```python
# firmware/main.py (ESP32-S3 MicroPython)
import machine
import network
import ujson
import time
import gc
from lib.keller import KellerReader
from lib.mqtt_client import MQTTClient
from lib.buffer import OfflineBuffer

# ── Configuration ──────────────────────────────────────────
WIFI_SSID = "..."
WIFI_PASS = "..."
MQTT_BROKER = "..."
MQTT_PORT = 8883
GATEWAY_MAC = "AA:BB:CC:11:22:33"
SENSOR_CONFIG = [...]  # Serial numbers, addresses, channels

# ── State Management ───────────────────────────────────────
class GatewayState:
    """Immutable gateway state stored in flash."""
    def __init__(self, mac, sensors):
        self.mac = mac
        self.sensors = sensors  # List of (serial_number, address, channels)
        self.reading_interval = 300  # seconds
        self.last_readings = {}

# ── Offline Buffer ─────────────────────────────────────────
class OfflineBuffer:
    """Store readings locally when network is unavailable."""
    def __init__(self, max_size=10000):
        self.buffer = []
        self.max_size = max_size
        self.file = "/buffer/readings.json"

    def add(self, reading):
        self.buffer.append(reading)
        if len(self.buffer) > self.max_size:
            self.buffer = self.buffer[-self.max_size:]
        self._flush_to_flash()

    def drain(self):
        """Return all buffered readings and clear buffer."""
        readings = self.buffer[:]
        self.buffer.clear()
        self._flush_to_flash()
        return readings

    def _flush_to_flash(self):
        try:
            with open(self.file, 'w') as f:
                ujson.dump(self.buffer, f)
        except OSError:
            pass  # Flash full, oldest data lost

# ── Main Loop ──────────────────────────────────────────────
def main():
    gc.collect()  # Critical for memory management

    # Connect WiFi
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(WIFI_SSID, WIFI_PASS)
    while not wlan.isconnected():
        time.sleep(1)

    # Initialize MQTT
    mqtt = MQTTClient(
        client_id=GATEWAY_MAC,
        server=MQTT_BROKER,
        port=MQTT_PORT,
        ssl=True,
        ssl_params={'certfile': '/certs/client.pem'}
    )

    # Initialize Keller readers
    kellers = {
        sn: KellerReader(addr, pressure_ch, temp_ch)
        for sn, addr, pressure_ch, temp_ch in SENSOR_CONFIG
    }

    # Load offline buffer
    buffer = OfflineBuffer()
    try:
        with open(buffer.file) as f:
            buffered = ujson.load(f)
    except:
        buffered = []

    # Main loop
    while True:
        try:
            gc.collect()  # Prevent memory leaks

            readings = []
            for sn, reader in kellers.items():
                try:
                    pressure = reader.read_pressure()
                    temp = reader.read_temperature()
                    readings.append({
                        "serial_number": sn,
                        "pressure_bar": pressure,
                        "temperature_c": temp,
                        "status": 0,
                        "timestamp": int(time.time())
                    })
                except Exception as e:
                    readings.append({
                        "serial_number": sn,
                        "status": 1,  # Error
                        "timestamp": int(time.time())
                    })

            # Publish reading
            payload = ujson.dumps({
                "gateway_mac": GATEWAY_MAC,
                "timestamp": int(time.time()),
                "sensors": readings
            })

            mqtt.publish(f"fuel/{GATEWAY_MAC}/readings", payload, qos=1)

            # Drain offline buffer if connected
            if buffered:
                mqtt.publish(f"fuel/{GATEWAY_MAC}/readings", ujson.dumps({
                    "gateway_mac": GATEWAY_MAC,
                    "timestamp": int(time.time()),
                    "sensors": buffered
                }), qos=1)
                buffered.clear()

            time.sleep(GATEWAY_STATE.reading_interval)

        except KeyboardInterrupt:
            break
        except Exception as e:
            # Store in offline buffer on error
            buffer.add(readings)
            time.sleep(10)
            gc.collect()

if __name__ == "__main__":
    main()
```

### 2.4 Command Interface Implementation

```python
# Edge command handler (server-side)
class GatewayCommandHandler:
    """Handle bi-directional commands to/from ESP32 gateways."""

    COMMANDS = {
        "get_config": "fuel/{mac}/cmd/get_config",
        "set_interval": "fuel/{mac}/cmd/set_interval",
        "reboot": "fuel/{mac}/cmd/reboot",
        "diagnose": "fuel/{mac}/cmd/diagnose",
        "update_firmware": "fuel/{mac}/cmd/update_firmware",
    }

    def send_command(self, gateway_mac: str, command: str, params: dict = None):
        """Send a command to a gateway."""
        topic = f"fuel/{gateway_mac}/cmd"
        payload = ujson.dumps({"command": command, "params": params or {}})
        self.mqtt_client.publish(topic, payload, qos=1)

    def on_response(self, client, userdata, msg):
        """Handle gateway responses."""
        topic = msg.topic
        gateway_mac = topic.split("/")[1]
        payload = ujson.loads(msg.payload.decode('utf-8'))
        logger.info(f"Response from {gateway_mac}: {payload}")
```

---

## Phase 3: High Availability (Weeks 5-6)

### 3.1 Multi-Instance Ingestion Service

```yaml
# docker-compose.yml (production)
version: '3.8'
services:
  # ── MQTT Broker Cluster ──
  mosquitto-1:
    image: eclipse-mosquitto:2
    ports: ["1883:1883", "8883:8883"]
    volumes:
      - ./mosquitto/mosquitto1.conf:/mosquitto/config/mosquitto.conf
    deploy:
      replicas: 3
      mode: replicated

  # ── Ingestion Services ──
  ingestion-service:
    build: .
    deploy:
      replicas: 4
      resources:
        limits: { cpus: '2', memory: 1024M }
    environment:
      - MQTT_BROKER=mosquitto-cluster
      - MQTT_PORT=1883
      - REDIS_URL=redis://redis-cluster:6379/0
      - DATABASE_URL=postgresql://user:pass@db:5432/fuel_tank
    depends_on: [mosquitto-1, redis-cluster]

  # ── Celery Workers ──
  celery-worker:
    build: .
    deploy:
      replicas: 4
      resources:
        limits: { cpus: '1', memory: 512M }
    command: celery -A celery_app worker --concurrency=4 --queues=ingestion,analytics,notifications
    environment:
      - REDIS_URL=redis://redis-cluster:6379/0

  # ── Celery Beat (Scheduled Tasks) ──
  celery-beat:
    build: .
    deploy:
      replicas: 1
    command: celery -A celery_app beat --schedule=/tmp/celery_schedule.json
    environment:
      - REDIS_URL=redis://redis-cluster:6379/0

  # ── Flask Web Application ──
  web-app:
    build: .
    deploy:
      replicas: 3
      resources:
        limits: { cpus: '1', memory: 512M }
    ports: ["5000:5000"]
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/fuel_tank
      - REDIS_URL=redis://redis-cluster:6379/0

  # ── PostgreSQL + TimescaleDB ──
  postgres:
    image: timescale/timescaledb:latest-pg16
    deploy:
      replicas: 1
    volumes:
      - pg_data:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: fuel_tank
      POSTGRES_USER: fuel_tank_user
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    resources:
      limits: { cpus: '4', memory: 8G }

  # ── Redis Cluster ──
  redis-cluster:
    image: redis:7
    deploy:
      replicas: 3
    volumes:
      - redis_data:/data

volumes:
  pg_data:
  redis_data:
```

### 3.2 Load Balancer Configuration

```nginx
# nginx.conf — WebSocket support for real-time dashboards
upstream web_backend {
    least_conn;
    server web-app-1:5000 max_fails=3 fail_timeout=30s;
    server web-app-2:5000 max_fails=3 fail_timeout=30s;
    server web-app-3:5000 max_fails=3 fail_timeout=30s;
}

server {
    listen 443 ssl http2;
    server_name fuel-monitoring.example.com;

    # WebSocket support for SSE
    location /tank-updates {
        proxy_pass http://web_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }

    # Regular API routes
    location / {
        proxy_pass http://web_backend;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api:10m rate=100r/m;
    location /api/ {
        limit_req zone=api burst=20;
        proxy_pass http://web_backend;
    }
}
```

### 3.3 Monitoring & Alerting Stack

```yaml
# monitoring/docker-compose.monitoring.yml
  # ── Prometheus ──
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
    ports: ["9090:9090"]

  # ── Grafana ──
  grafana:
    image: grafana/grafana:latest
    ports: ["3000:3000"]
    volumes:
      - grafana_data:/var/lib/grafana

  # ── Node Exporter (server metrics) ──
  node-exporter:
    image: prom/node-exporter:latest
    ports: ["9100:9100"]
```

---

## Phase 4: Advanced Features (Weeks 7-8)

### 4.1 Edge Offline Buffering Strategy

```
┌─────────────────────────────────────────────────────┐
│                 ESP32-S3 Gateway                    │
│                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ Sensors  │→│ Buffer   │→│ MQTT Client      │  │
│  │ (RS485)  │  │ (LRU)    │  │ (TLS)            │  │
│  └──────────┘  └──────────┘  └──────────────────┘  │
│       │              │                      │       │
│       │         ┌────▼────┐            ┌────▼────┐  │
│       │         │ Flash   │            │ Network │  │
│       │         │ Buffer  │            │ Status  │  │
│       │         │ 10K     │            │ Monitor │  │
│       │         │ entries │            │         │  │
│       └─────────┴─────────┘            └─────────┘  │
└─────────────────────────────────────────────────────┘
```

**Buffer Strategy:**
- **In-memory buffer**: 100 most recent readings (circular buffer)
- **Flash buffer**: 10,000 readings stored in SPIFFS/LittleFS
- **Priority**: Critical alarms are sent immediately (not buffered)
- **Recovery**: On reconnection, drain flash buffer first, then stream at 2x rate
- **TTL**: Buffered readings older than 7 days are discarded

### 4.2 Disaster Recovery Plan

```
┌─────────────────────────────────────────────────────┐
│                Disaster Recovery                     │
│                                                     │
│  • Database: Daily automated backups (pg_dump)      │
│  • Point-in-time recovery: WAL archiving            │
│  • MQTT broker: Persistent sessions + QoS 1         │
│  • Edge devices: 7-day offline buffer               │
│  • Config: GitOps with versioned deployments        │
│  • Failover: Auto-promote read replicas             │
│                                                     │
│  Recovery Time Objective (RTO): 15 minutes          │
│  Recovery Point Objective (RPO): 5 minutes          │
└─────────────────────────────────────────────────────┘
```

### 4.3 Auto-scaling Rules

| Metric | Threshold | Action |
|--------|-----------|--------|
| CPU > 70% for 5 min | Scale up Celery workers | +2 workers |
| Memory > 80% | Scale up ingestion | +1 instance |
| MQTT queue depth > 10K | Scale up ingestion | +1 instance |
| DB connection pool > 80% | Scale up DB | +1 connection |
| Alert backlog > 1000 | Scale up Celery | +2 workers |

---

## Phase 5: Performance Validation

### 5.1 Load Testing Plan

```python
# tests/load_test_ingestion.py
"""
Load test the ingestion service with simulated gateway data.
Target: 1000 gateways × 10 tanks × 12 readings/min = 120K/hour
"""
import asyncio
import json
import time
from locust import HttpUser, task, between

class GatewaySimulator(HttpUser):
    wait_time = between(0.1, 0.5)

    @task
    def send_readings(self):
        """Simulate a gateway sending readings."""
        payload = {
            "gateway_mac": "AA:BB:CC:11:22:33",
            "timestamp": int(time.time()),
            "sensors": [
                {
                    "serial_number": i,
                    "pressure_bar": 1.0 + (i * 0.1),
                    "temperature_c": 23.0,
                    "status": 0,
                    "timestamp": int(time.time())
                }
                for i in range(1, 11)  # 10 sensors per gateway
            ]
        }
        self.client.post("/mqtt/test", json=payload)
```

### 5.2 Performance Benchmarks (Target)

| Metric | Current | Target (1000 GW) | Improvement |
|--------|---------|-------------------|-------------|
| Measurements/hour | ~7,200 | 120,000 | 16.7x |
| DB write latency | <50ms | <10ms | 5x |
| Dashboard query time | <2s | <200ms | 10x |
| Alert dispatch time | <5s | <500ms | 10x |
| Gateway connection time | <3s | <1s | 3x |
| Memory usage per GW | ~10MB | ~2MB | 5x |
| Uptime | ~99% | 99.95% | - |

---

## Deployment Checklist

### Pre-Deployment
- [ ] All secrets in environment variables / Vault
- [ ] TLS certificates generated and deployed
- [ ] Database backups verified and tested
- [ ] Redis persistence configured (AOF + RDB)
- [ ] TimescaleDB compression verified
- [ ] ESP32-S3 firmware compiled and OTA-ready
- [ ] Load balancer configured with health checks
- [ ] Monitoring stack deployed (Prometheus + Grafana)
- [ ] Alert rules configured for system metrics

### Deployment Steps
1. Deploy PostgreSQL + TimescaleDB with migration script
2. Deploy Redis cluster
3. Deploy Celery infrastructure (workers + beat)
4. Deploy MQTT broker cluster
5. Deploy ingestion services (4 instances)
6. Deploy web application (behind load balancer)
7. Deploy monitoring stack
8. Flash ESP32-S3 gateways with firmware
9. Run load test to validate 1000+ gateway capacity
10. Monitor for 48 hours, adjust scaling rules

### Post-Deployment
- [ ] Verify all gateways are connected and reporting
- [ ] Verify continuous aggregates are refreshing
- [ ] Verify compression policies are active
- [ ] Verify alarm notifications are dispatching
- [ ] Verify dashboard queries are <200ms
- [ ] Set up automated backups and retention
- [ ] Document runbooks for incident response
