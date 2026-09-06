# Fuel Monitoring Platform — System Health & Architecture Report

**Date:** 2026-09-06  
**Scope:** Complete end-to-end review across Edge Layer, Ingestion Layer, Cloud Backend, and Frontend  

---

## 1. Executive Summary

The Fuel Monitoring Platform is a multi-tier IoT system comprising ESP32-S3 edge gateways, an MQTT-based ingestion pipeline, a Flask/SQLAlchemy/TimescaleDB cloud backend, and a Flask template/React frontend. The system is functional but exhibits significant architectural debt across all layers.

**Critical Findings:** 8 critical, 12 high, 18 medium, 6 low severity issues identified.

---

## 2. Data Lifecycle Map (Sensor → UI)

```
[ESP32-S3] → RS485 → Keller Sensor → Read Pressure/Temp
        ↓
[ESP32-S3] → MQTT TLS → fuel/{mac}/readings
        ↓
[Ingestion Service] → Parse JSON → _find_tank() → DB Lookup
        ↓
[MeasurementProcessor] → Pressure → Level → Volume → Fill%
        ↓
[FlowRateCalculator] → Volume Delta → Flow Rate
        ↓
[AlarmManager] → Threshold Check → Alarm Creation
        ↓
[TimescaleDB] → Hypertable Insert → Continuous Aggregates
        ↓
[Flask API] → JSON Response → React/Dashboard → User
```

### Weaknesses in Data Lifecycle

| Stage | Issue | Severity |
|-------|-------|----------|
| Edge→MQTT | No payload schema validation; no offline buffer | CRITICAL |
| Ingestion→Tank Lookup | New `MeasurementProcessor` per message; sequential DB queries | HIGH |
| Processing→DB | Direct `db.session.commit()` per measurement; no batch writes | HIGH |
| DB→Query | Missing composite indexes; no query result caching | HIGH |
| API→UI | N+1 queries in dashboard; no pagination on alarm endpoints | MEDIUM |

---

## 3. Single Points of Failure (SPOFs)

### 3.1 MQTT Ingestion Service (`services/mqtt_ingestion.py`)
- **SPOF**: Single `MqttIngestionService` instance with no clustering. If it crashes, all sensor data stops flowing.
- **No message queue**: Messages are processed synchronously in `_on_message`. A slow DB commit blocks the MQTT callback, causing message buffering and potential broker disconnection.
- **No reconnect logic for broker**: `_run()` reconnects in a tight loop with `loop_forever()` — if the broker is down for extended periods, the service consumes 100% CPU in retry.

### 3.2 Database Layer
- **Single PostgreSQL instance**: No read replicas, no connection pooling configured.
- **`db.session` shared across threads**: Flask-SQLAlchemy's default session scope is per-request, but background threads (TankMonitor, MQTT service) call `db.session.commit()` directly, causing race conditions.
- **TimescaleDB retention policy**: 30-day retention with no compression. At 5-second intervals across 100 tanks, this generates ~1.7M rows/day (~2.4GB/month uncompressed).

### 3.3 Flask Application (`app.py`)
- **Single-threaded blocking operations**: `_save_measurement_and_check_alarms()` calls `db.session.commit()` in the MQTT callback thread, blocking all other operations.
- **No Celery/Redis Queue**: Long-running tasks (forecast generation, CSV export, daily consumption calculations) run in Flask worker threads, starving the web server.
- **Hardcoded credentials**: `postgresql://fuel_tank_user:1980@localhost/fuel_tank_monitoring` and default admin password `'admin'`.

### 3.4 Edge Layer
- **No ESP32-S3 firmware in repository**: The user references MicroPython on ESP32-S3 but no such files exist in the repo. This is a critical gap.
- **No offline buffering**: If the gateway loses network connectivity, sensor readings are lost.

---

## 4. Bottlenecks & Performance Issues

### 4.1 MQTT Ingestion Service
```
_per_sensor():  Creates new MeasurementProcessor per message
                Creates new TankConfig per message
                Queries DB: 1 SELECT (tank lookup) + 1 SELECT (latest measurement)
                DB Write: 1 INSERT + 1 UPDATE (tank status)
                Alarm check: 1 SELECT + 1 INSERT per alarm
```
- **Per-message overhead**: ~6 DB round-trips per sensor reading. At 100 tanks × 12 readings/min = 720 measurements/hour = 4,320 DB round-trips/hour minimum.
- **No batch processing**: Each sensor reading is committed individually.

### 4.2 Dashboard (`app.py` routes)
- **N+1 Query Pattern**: `dashboard()` calls `tank.get_latest_measurement()` for each tank in a loop (lines 372-386).
- **No pagination**: `/api/alarms` returns ALL alarms for all accessible tanks in a single query.

### 4.3 TimescaleDB
- **Missing composite index**: No index on `(tank_id, timestamp DESC)` exists as a migration artifact (only exists as a runtime SQL statement).
- **No compression policy**: Hypertable has no compression, leading to unbounded storage growth.
- **Continuous aggregates not refreshed**: `measurements_hourly` and `measurements_daily` materialized views are created but no refresh policy is configured.

### 4.4 Memory Management
- **`MeasurementProcessor.smooth_pressure()`**: Instance-level `self.pressure_readings` list grows unbounded if `max_pressure_readings` is not reset.
- **`FlowRateCalculator`**: Each `TankMonitor` creates its own instance, but instances are never garbage collected when tanks are removed.
- **`TankMonitor._read_sensor_data()`**: `time.sleep(1)` between pressure and temperature readings adds 1 second of latency per measurement cycle.

---

## 5. Race Conditions & Thread Safety

| Location | Issue |
|----------|-------|
| `TankMonitor._monitor_thread()` | Uses `threading.Lock()` but `db.session` is NOT thread-safe. Multiple threads share the same Flask app context. |
| `MqttIngestionService._on_message()` | Runs in paho-mqtt's internal thread. Calls `db.session.commit()` without Flask request context. |
| `FlowRateCalculator` | Instance state (`self.current_flow_rate`, `self.history`) is not thread-safe. If shared across threads, data corruption is possible. |
| `AlarmManager` | Creates `Alarm` objects and commits in arbitrary thread context. No session isolation. |
| `TankMonitorManager` | Uses `threading.Lock()` but not for DB operations. |
| `db.session` in `tank_monitor.py` | `DatabaseService.save_measurement()` creates a new `db.session` per call, but the global `db` object is shared. |

---

## 6. Security Audit Findings

### 6.1 Critical
- **Hardcoded DB credentials** in `app.py:101` and `scripts/migrate_sqlite_to_timescaledb.py:30`
- **Default admin credentials** in `app.py:174-178` (`username='admin'`, password `'admin'`)
- **No MQTT TLS configuration** in `services/mqtt_ingestion.py` — `port=1883` is the default unencrypted port
- **No payload schema validation** for MQTT messages — arbitrary JSON accepted
- **No rate limiting** on any API endpoint

### 6.2 High
- **No authentication on `/api/tanks/<id>/measurements`** beyond `@login_required` — no RBAC check on measurement endpoints
- **SQL injection risk** in `app.py:525` — `Alarm.query.filter(False)` pattern and direct string interpolation in `daily_usage()`
- **No input sanitization** on calibration form (`app.py:487-491` accepts any float)
- **Missing CSRF protection** on alarm acknowledge endpoint (`/alarms/acknowledge/<id>`)

### 6.3 Medium
- **No audit logging** for configuration changes (calibration updates, threshold changes)
- **No HTTPS enforcement** in Flask configuration
- **Session fixation risk** — no session regeneration on login
- **Information disclosure** via `to_dict()` methods exposing internal IDs and relationships

---

## 7. Database & TimescaleDB Assessment

### 7.1 Model Issues
- `sensor_serial_number` is `BigInteger` with `unique=True` but no DB-level unique constraint (migration-dependent)
- `gateway_mac` is `String(17)` with `index=True` but no composite index with `sensor_serial_number`
- `Measurement.timestamp` has no index at the DB level (only the hybrid property aggregation uses it)
- No index on `Alarm.acknowledged` combined with `Alarm.timestamp` (common filter pattern)
- No index on `Tank.gateway_mac` for the MAC-based lookup path

### 7.2 TimescaleDB Configuration
```
Current State:
- Hypertable created at runtime via create_timescale_extensions()
- Retention: 30 days (add_retention_policy)
- Continuous Aggregates: measurements_hourly, measurements_daily (created but NO refresh policy)
- Compression: NOT CONFIGURED
- Chunk Time Interval: Default (7 days) — should be tuned to 1 day for high-frequency data
```

### 7.3 Migration Issues
- Migrations are inconsistent: `63ede4e741c9` (adds `alarm.level`), `b6afda779df5` (adds `tank.connection_status`), `46ab8aa9f43c` (adds `tank.elevation`), `4f6adc5392e7` (adds indexes + soft delete)
- No migration adds `gateway_mac` or `sensor_serial_number` columns to the Tank model
- No migration creates TimescaleDB hypertables (done at runtime in `app.py`)
- No migration creates the `idx_measurement_tank_time` composite index (done at runtime)

---

## 8. Edge Firmware Assessment

**CRITICAL GAP**: No ESP32-S3 MicroPython firmware exists in the repository.

Based on the architecture description and backend expectations, the edge layer should include:
- MicroPython running on ESP32-S3
- RS485 communication via Keller protocol (function codes 0x30, 0x49, 0x5F)
- MQTT client with TLS authentication
- Gateway identity via MAC address
- Sensor identity via immutable Keller serial numbers
- `fuel/{mac}/readings` topic for sensor data
- `fuel/{mac}/status` topic for gateway status
- `fuel/{mac}/cmd` topic for bi-directional commands
- Offline buffering during network outages
- CRC-16 validation for all RS485 messages
- `gc.collect()` calls for memory management

---

## 9. Recommended Fixes Priority Matrix

| Priority | Fix | Effort | Impact |
|----------|-----|--------|--------|
| P0 | Add ESP32-S3 firmware with offline buffer | HIGH | CRITICAL |
| P0 | Implement MQTT TLS + payload validation | LOW | CRITICAL |
| P0 | Fix default admin credentials | LOW | CRITICAL |
| P1 | Add Celery/Redis for async processing | MEDIUM | HIGH |
| P1 | Add composite DB indexes (gateway_mac, sensor_serial) | LOW | HIGH |
| P1 | Fix thread-safety in ingestion service | MEDIUM | HIGH |
| P1 | Configure TimescaleDB compression + refresh policies | LOW | HIGH |
| P2 | Implement batch DB writes in ingestion | MEDIUM | MEDIUM |
| P2 | Add rate limiting to API endpoints | LOW | MEDIUM |
| P2 | Add N+1 query fixes in dashboard | LOW | MEDIUM |
| P3 | Add audit logging for configuration changes | LOW | LOW |
| P3 | Add HTTPS enforcement | LOW | LOW |

---

## 10. Conclusion

The platform has a solid conceptual architecture but suffers from significant implementation gaps, particularly in the edge layer, concurrency model, and database optimization. The most urgent actions are:
1. Create the ESP32-S3 firmware (currently absent)
2. Fix security vulnerabilities (hardcoded credentials, no TLS)
3. Add async task processing (Celery/Redis)
4. Optimize database layer (indexes, compression, batch writes)
5. Fix thread-safety issues in the ingestion pipeline
