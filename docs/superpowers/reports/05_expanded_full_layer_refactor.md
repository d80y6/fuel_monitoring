# Expanded Full-Layer Refactor Report

**Date:** 2026-09-06
**Scope:** Complete production-ready refactored code for all 4 layers

---

## Summary of Changes

| Layer | Files Modified | Files Created | Critical Fixes |
|-------|---------------|---------------|----------------|
| Firmware (Edge) | 6 files rewritten | 0 | Main loop wiring, buffer recursion, UART leak, watchdog |
| Backend Models | 8 files rewritten | 0 | SoftDeleteMixin, N+1 queries, thread safety, missing imports |
| Ingestion & Services | 7 files rewritten | 0 | Redis cache, batch writes, Celery wiring, notifications |
| Frontend & Security | 5 files modified | 2 new | XSS, CSRF, rate limiting, session fixation, CSP headers |

---

## Layer 1: Firmware (Edge) — All Files Rewritten

### `firmware/main.py`
- **Fixed:** `check_wifi()` implemented with exponential backoff
- **Fixed:** `MQTTClient` instantiated and wired to main loop
- **Fixed:** `CommandHandler` connected via `set_command_handler()`
- **Fixed:** `readings = []` initialized before try/except (no more NameError)
- **Fixed:** `mqtt_connected()` and `publish_readings()` helper functions
- **Added:** Hardware watchdog timer (`machine.WDT(timeout=30000)`)
- **Added:** `reader_cache` — reuses `KellerReader` instances per sensor address
- **Added:** Config loaded from `firmware.json` (no hardcoded values)
- **Added:** `cleanup()` in `finally` block — closes UARTs, disconnects MQTT

### `firmware/lib/keller.py`
- **Fixed:** Variable-length response reads via `_expected_response_length()`
- **Fixed:** DE pin timing — calculated byte-time delay + `uart.any()` polling
- **Fixed:** Single-endian CRC validation (removed dual-endian check)
- **Fixed:** Configurable UART pins via constructor
- **Fixed:** Consistent `raise ConnectionError()` (never returns None)

### `firmware/lib/mqtt_client.py`
- **Fixed:** `_on_message` properly registered as callback
- **Fixed:** `CommandHandler` wired via `set_command_handler()` — no inline command routing
- **Fixed:** Bounded in-memory buffer (`_max_buffered` parameter)
- **Fixed:** Exponential backoff on reconnection
- **Fixed:** Deferred `machine.reset()` — uses `request_reset()` flag
- **Fixed:** `drain_buffer()` — pops one item, breaks on failure (no infinite loop)

### `firmware/lib/buffer.py`
- **Fixed:** Iterative trimming in `_flush_to_flash()` (no recursion)
- **Fixed:** Atomic drain — writes `'[]'` to file before clearing memory
- **Fixed:** Type validation in `add()` (accepts list or dict only)
- **Fixed:** Batch flush — `_dirty_count` tracks writes, flushes every N adds
- **Fixed:** `KeyError` handling in `_load_from_flash()`

### `firmware/lib/command_handler.py`
- **Fixed:** `gc`, `network`, `uos` imported at module level
- **Fixed:** `_get_sensor_status()` reads actual UART status
- **Fixed:** `_update_firmware()` implements OTA via `urequests` + `esp.flash_write()`
- **Fixed:** `_reboot()` — no dead return after `machine.reset()`
- **Added:** `execute_from_mqtt()` bridge method for MQTT callback wiring
- **Added:** `close_readers()` for UART cleanup

### `firmware/firmware.json`
- **Fixed:** SPIFFS partition: 655360 → 1835008 bytes (~1.75MB)
- **Added:** `gateway`, `wifi`, `mqtt`, `uart`, `watchdog` configuration sections

---

## Layer 2: Backend Models — All Files Rewritten

### `models/database.py`
- **Fixed:** `SoftDeleteMixin` applied to User, Company, Site, Tank (removed duplicate implementations)
- **Fixed:** `datetime.datetime.now()` → `func.now()` for DB defaults
- **Fixed:** N+1 in `Alarm.to_dict()` — documented + added `to_dict_loaded()` for pre-loaded queries
- **Fixed:** Added composite indexes: `ix_tank_site_active`, `ix_measurement_tank_timestamp`, `ix_alarm_tank_type_acknowledged`
- **Fixed:** Removed duplicate `current_volume` property on Tank
- **Fixed:** `create_timescale_extensions()` — uses raw psycopg2 via `_get_raw_connection(engine)`
- **Fixed:** `setup_timescale_retention()` — removed regex URI parsing, uses `engine.url` directly

### `models/base_model.py`
- **Fixed:** Added missing `datetime` import
- **Fixed:** Added `Decimal` handling in `to_dict()`

### `models/measurement_processor.py`
- **Fixed:** Thread-safe — `Lock` on `_pressure_window`, `_last_level`, `_last_volume`
- **Fixed:** Initialized `_last_level = None` and `_last_volume = None` in `__init__`
- **Fixed:** Clamped negative pressure to `0.0`
- **Fixed:** Removed no-op `* 1000 * 0.001` in `get_stable_volume()`
- **Fixed:** Uses `datetime.utcnow()` instead of `datetime.now()`

### `models/flow_rate_calculator.py`
- **Fixed:** Thread-safe — `Lock` protecting all mutable state
- **Fixed:** `self.history[-1]` directly instead of `list(self.history)[-1]`
- **Fixed:** Added `LEAK_DETECTED` state to FlowState enum
- **Fixed:** Leak detection — `_check_leak_detection()` tracks sustained negative flow

### `models/alarm_manager.py`
- **Fixed:** Duplicate alarm prevention — cooldown per alarm type (default 300s)
- **Fixed:** `level` field now set on created alarms
- **Fixed:** `db.session.get(Alarm, alarm_id)` instead of deprecated `Alarm.query.get()`
- **Fixed:** Consistent session management — all queries use `self.db_session`

### `models/tank_monitor.py`
- **Fixed:** Removed duplicate `smooth_pressure()` — delegates to `self.processor.smooth_pressure()`
- **Fixed:** `db.session.get(Tank, id)` instead of `Tank.query.get()`

### `models/tank_config.py`
- **Added:** `to_dict()` / `from_dict()` for Redis serialization
- **Added:** `to_json()` / `from_json()` convenience methods
- **Fixed:** Horizontal tank volume calculation properly named and documented

### `models/__init__.py`
- **Added:** Proper re-exports of all public classes

---

## Layer 3: Ingestion & Services — All Files Rewritten

### `services/mqtt_ingestion.py`
- **Added:** JSON schema validation (`READING_SCHEMA`, `STATUS_SCHEMA`)
- **Added:** Redis-backed LRU cache (`_RedisLRUCache` class)
- **Added:** Batch DB writes — thread-safe buffer, flushes every 50 items or 5 seconds
- **Wired:** `FlowRateCalculator` per tank (not inline simplified calculation)
- **Added:** TLS configuration (ca_cert, client_cert, client_key)
- **Added:** Bidirectional command publishing (reconfigure, set_interval, reboot, diagnose)
- **Added:** Exponential backoff on reconnection (doubles up to 120s)

### `tasks/ingestion.py`
- **Fixed:** `process_measurements` — `autoretry_for`, `retry_backoff=True`, `retry_jitter=True`
- **Fixed:** `check_alarms` — dispatches `send_notification.delay()` for each triggered alarm
- **Fixed:** `cleanup_old_measurements` — tries TimescaleDB `drop_chunks()` first

### `tasks/notifications.py`
- **Implemented:** Actual email via SMTP with TLS
- **Added:** Recipient resolution from Tank → Site → Company → User relationships
- **Added:** Notification deduplication via Redis TTL key (1 hour)
- **Added:** Exponential backoff on retry

### `tasks/analytics.py`
- **Fixed:** N+1 — batch process tanks with single subquery join
- **Fixed:** Specific exception types (`ValueError` catches)
- **Fixed:** Module-level imports (not inside tank loop)
- **Added:** Task time limits (`task_time_limit=600`)

### `tasks/export.py`
- **Added:** Date range filtering (`start_date`/`end_date` or relative `days`)
- **Fixed:** Stream to file in 1000-row batches (not StringIO)
- **Fixed:** Returns download URL, not CSV content in Redis

### `celery_app.py`
- **Fixed:** Flask app context properly available to all tasks
- **Added:** Exponential backoff configuration globally
- **Added:** Task timeouts (`task_time_limit=600`, `task_soft_time_limit=540`)

---

## Layer 4: Frontend & Security — Modified + New Files

### New: `utils/rate_limiter.py`
- `SlidingWindowRateLimiter` using Redis sorted sets
- Pre-configured: `login_limiter` (5/15min), `password_reset_limiter` (3/1hr), `api_limiter` (60/min)
- `@rate_limit(limiter)` decorator for Flask routes
- Fail-open when Redis unavailable

### New: `utils/security.py`
- CSP headers (scripts/styles to self + CDN)
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- HSTS (when HTTPS), removes `Server` header
- HTTPS redirect when `FORCE_HTTPS` enabled

### `config.py`
- **Added:** `DevelopmentConfig`, `TestingConfig`, `ProductionConfig` subclasses
- **Removed:** `save_to_env_file()` (was destroying .env)
- **Added:** Production config raises `RuntimeError` if SECRET_KEY missing
- **Added:** Session security settings (`SESSION_COOKIE_SECURE`, `SAMESITE`)

### `auth.py`
- **Added:** Rate limiting on login and password reset endpoints
- **Fixed:** Session regeneration before `login_user()` (prevent session fixation)
- **Fixed:** Removed broken dual-path form/request.form validation
- **Added:** Open redirect protection on `next` parameter
- **Implemented:** Real password reset with HMAC token (1-hour expiry)

### `app.py`
- **Fixed:** XSS — `tank.name|tojson` in template data
- **Added:** CSRF on alarm acknowledge (CSRF token in JS)
- **Added:** RBAC check on all API endpoints (`check_tank_access()`)
- **Added:** Rate limiting middleware on all API endpoints
- **Removed:** Hardcoded admin credentials (replaced with CLI instructions)
- **Fixed:** SSE via Redis pub/sub (not polling DB every 2 seconds)
- **Added:** `init_rate_limiter(app)` and `init_security_middleware(app)` at startup

### `templates/tank_detail.html` (line 357)
```javascript
// BEFORE (vulnerable):
name: "{{ tank.name }}"

// AFTER (safe):
name: {{ tank.name|tojson }}
```

### `static/js/tank_detail.js`
- **Fixed:** Alarm acknowledge URL path
- **Added:** CSRF token extraction and `X-CSRFToken` header on POST
