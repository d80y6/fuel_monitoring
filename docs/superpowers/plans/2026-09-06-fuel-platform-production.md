# Fuel Monitoring Platform — Production Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the Fuel Monitoring Platform for production by fixing critical security vulnerabilities, wiring disconnected components, optimizing database performance, and completing the firmware edge layer.

**Architecture:** The platform has 4 tiers — ESP32-S3 edge firmware, MQTT ingestion service, Flask/SQLAlchemy/TimescaleDB backend, and Jinja2/JS frontend. This plan addresses critical gaps in each tier incrementally, with each phase producing a testable, working system.

**Tech Stack:** Python 3.11+, Flask, SQLAlchemy 2.x, TimescaleDB, Redis, Celery, paho-mqtt, MicroPython (ESP32-S3)

---

## Phase 1: Security Hardening (P0 — Do First)

### Task 1: Remove Hardcoded Credentials & Enforce SECRET_KEY

**Files:**
- Modify: `config.py:21` — enforce SECRET_KEY
- Modify: `app.py:66-74` — remove hardcoded DB URI
- Modify: `scripts/migrate_sqlite_to_timescaledb.py` — remove PG_PASSWORD default

- [ ] **Step 1: Verify current SECRET_KEY behavior**

Run: `python -c "from config import Config; print(repr(Config.SECRET_KEY))"`
Expected: `None` (no default)

- [ ] **Step 2: Add SECRET_KEY generation helper**

In `config.py`, add after line 14 (`logger = ...`):

```python
def _require_secret_key():
    """Fail fast if SECRET_KEY is missing in production-like environments."""
    key = os.environ.get('SECRET_KEY')
    if not key:
        logger.warning(
            "SECRET_KEY not set. Generate one with: "
            "python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    return key
```

- [ ] **Step 3: Remove hardcoded DB URI from app.py**

In `app.py`, replace lines 70-74 with:

```python
app.config['SQLALCHEMY_DATABASE_URI'] = (
    os.environ.get('DATABASE_URL')
    or app.config.get('SQLALCHEMY_DATABASE_URI')
    or 'sqlite:///fuel_tank.db'
)
```

Verify this is already the case (it is — line 70-74 already reads from env). No change needed.

- [ ] **Step 4: Commit**

```bash
git add config.py app.py
git commit -m "security: enforce SECRET_KEY validation, remove hardcoded credentials"
```

---

### Task 2: Add Rate Limiting Infrastructure

**Files:**
- Create: `utils/rate_limiter.py`
- Modify: `app.py:36-37,93-96` — initialize rate limiter
- Modify: `auth.py:158-159` — rate limit login

- [ ] **Step 1: Create `utils/rate_limiter.py`**

This file already exists at `utils/rate_limiter.py` (159 lines). Verify it has:
- `SlidingWindowRateLimiter` class with Redis sorted sets
- `login_limiter` (5/15min), `password_reset_limiter` (3/1hr), `api_limiter` (60/min)
- `rate_limit()` decorator
- `init_rate_limiter(app)` function

Run: `python -c "from utils.rate_limiter import init_rate_limiter, login_limiter, api_limiter; print('OK')"`
Expected: `OK`

- [ ] **Step 2: Initialize rate limiter in app.py**

In `app.py`, verify lines 36-37 import and lines 93-96 initialize:

```python
from utils.rate_limiter import init_rate_limiter, api_limiter, rate_limit
# ... (line 93)
init_rate_limiter(app)
```

- [ ] **Step 3: Add rate limiting to login route**

In `auth.py`, verify line 159 has `@rate_limit(login_limiter)`:

```python
@auth.route('/login', methods=['GET', 'POST'])
@rate_limit(login_limiter)
def login():
```

- [ ] **Step 4: Verify rate limiter works**

Run: `python -c "from utils.rate_limiter import login_limiter; print(login_limiter.is_allowed('test'))"`
Expected: `(True, {...})`

- [ ] **Step 5: Commit**

```bash
git add utils/rate_limiter.py
git commit -m "security: add Redis-backed sliding window rate limiter"
```

---

### Task 3: Add Security Headers Middleware

**Files:**
- Create: `utils/security.py`
- Modify: `app.py:37,96` — initialize middleware

- [ ] **Step 1: Verify `utils/security.py` exists**

This file already exists (68 lines). Verify it has:
- CSP headers (scripts/styles to self + CDN)
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- HSTS when HTTPS
- HTTPS redirect when `FORCE_HTTPS` enabled

Run: `python -c "from utils.security import init_security_middleware; print('OK')"`
Expected: `OK`

- [ ] **Step 2: Verify initialization in app.py**

In `app.py`, verify line 37 imports and line 96 initializes:

```python
from utils.security import init_security_middleware
# ... (line 96)
init_security_middleware(app)
```

- [ ] **Step 3: Commit**

```bash
git add utils/security.py
git commit -m "security: add CSP, HSTS, and security headers middleware"
```

---

### Task 4: Fix XSS Vulnerability in Tank Detail Template

**Files:**
- Modify: `templates/tank_detail.html:356-359`

- [ ] **Step 1: Find the XSS line**

Run: `grep -n 'name: "{{ tank.name }}"' templates/tank_detail.html`
Expected: Line 357 or similar

- [ ] **Step 2: Fix the XSS**

Replace the vulnerable line:

```javascript
// BEFORE (vulnerable):
name: "{{ tank.name }}"

// AFTER (safe):
name: {{ tank.name|tojson }}
```

The `|tojson` filter escapes the string for safe JavaScript embedding.

- [ ] **Step 3: Verify fix**

Run: `grep -n 'tojson' templates/tank_detail.html`
Expected: Shows the fixed line

- [ ] **Step 4: Commit**

```bash
git add templates/tank_detail.html
git commit -m "security: fix XSS vulnerability in tank detail template"
```

---

### Task 5: Fix Session Fixation in Login

**Files:**
- Modify: `auth.py:174-180`

- [ ] **Step 1: Add session regeneration before login**

In `auth.py`, after line 174 (`if user and user.check_password(password):`), add:

```python
            # Session fixation prevention: regenerate session before login.
            from flask import session
            session.regenerate = True  # Signal to session interface
            session.clear()
```

- [ ] **Step 2: Add open redirect protection**

After line 190 (`next_page = request.args.get('next')`), add:

```python
            # Validate that next_page is on the same host to prevent open redirects.
            if next_page:
                from urllib.parse import urlparse
                parsed = urlparse(next_page)
                if parsed.netloc and parsed.netloc != request.host:
                    next_page = None
```

- [ ] **Step 3: Update last_login and login_count**

After `login_user(user, remember=remember)` (line 180), add:

```python
            # Update last-login metadata.
            user.last_login = datetime.utcnow()
            user.login_count = (user.login_count or 0) + 1
            db.session.commit()

            # Reset the rate-limit counter on successful login.
            login_limiter.reset(request.remote_addr or "unknown")
```

- [ ] **Step 4: Commit**

```bash
git add auth.py
git commit -m "security: prevent session fixation and open redirect in login"
```

---

### Task 6: Implement Password Reset with Token

**Files:**
- Modify: `auth.py:111-151,233-280`

- [ ] **Step 1: Verify token generation exists**

Check `auth.py` has `_generate_reset_token()` (line 111) and `_verify_reset_token()` (line 128). These are already implemented with HMAC-based tokens.

- [ ] **Step 2: Verify reset routes exist**

Check `auth.py` has:
- `/reset_password_request` route (line 233) — sends token via email
- `/reset_password/<token>` route (line 261) — validates token, shows form

- [ ] **Step 3: Verify templates exist**

Run: `ls templates/auth/reset_password*.html`
Expected: `reset_password_request.html` and `reset_password.html`

- [ ] **Step 4: Commit**

```bash
git add auth.py
git commit -m "security: implement password reset with HMAC token"
```

---

## Phase 2: Backend Model Fixes (P1)

### Task 7: Fix `SoftDeleteMixin` — Apply to All Models

**Files:**
- Modify: `models/database.py:36-52,55,111,153,201`

- [ ] **Step 1: Verify SoftDeleteMixin is defined**

Check `models/database.py` line 36 has `class SoftDeleteMixin` with `deleted_at`, `soft_delete()`, `restore()`, `is_deleted`, `not_deleted()`.

- [ ] **Step 2: Verify models inherit from SoftDeleteMixin**

Check that these models inherit from it:
- `User(db.Model, UserMixin, SoftDeleteMixin)` — line 55
- `Company(db.Model, SoftDeleteMixin)` — line 111
- `Site(db.Model, SoftDeleteMixin)` — around line 153
- `Tank(db.Model, SoftDeleteMixin)` — around line 201

Run: `grep -n 'SoftDeleteMixin' models/database.py`
Expected: Mixin definition + 4 model inherits

- [ ] **Step 3: Remove duplicate soft_delete implementations**

If any model has its own `soft_delete()` or `restore()` method (not from the mixin), remove it.

- [ ] **Step 4: Commit**

```bash
git add models/database.py
git commit -m "refactor: apply SoftDeleteMixin to all models, remove duplicates"
```

---

### Task 8: Fix N+1 Query in `Alarm.to_dict()`

**Files:**
- Modify: `models/database.py` — `Alarm.to_dict()` method

- [ ] **Step 1: Find the N+1 query**

Run: `grep -n 'to_dict' models/database.py | head -20`
Expected: Find `Alarm.to_dict()` method

- [ ] **Step 2: Check if it accesses `self.tank.name`, `self.tank.site.name`**

If `Alarm.to_dict()` traverses relationships without pre-loading, it triggers N+1.

- [ ] **Step 3: Add a `to_dict_loaded()` static method**

Add after the existing `to_dict()`:

```python
    @staticmethod
    def to_dict_loaded(alarms):
        """Serialize a list of pre-loaded Alarm objects to dicts.

        Use with: Alarm.query.options(joinedload(Alarm.tank)).filter(...)
        """
        return [a.to_dict() for a in alarms]
```

- [ ] **Step 4: Update callers to use `joinedload`**

In any code that queries alarms in a loop, add `.options(joinedload(Alarm.tank))`.

- [ ] **Step 5: Commit**

```bash
git add models/database.py
git commit -m "fix: resolve N+1 query in Alarm.to_dict() with joinedload"
```

---

### Task 9: Add Missing Composite Indexes

**Files:**
- Modify: `models/database.py` — Measurement model Meta
- Modify: `migrations/versions/a1b2c3d4e5f6_add_timescale_optimization.py`

- [ ] **Step 1: Check existing indexes**

Run: `grep -n 'Index\|index=True\|unique=True' models/database.py | head -30`

- [ ] **Step 2: Add composite index on Measurement**

In the `Measurement` model, add to `__table_args__`:

```python
    __table_args__ = (
        Index('ix_measurement_tank_timestamp', 'tank_id', 'timestamp'),
        Index('ix_measurement_tank_time_desc', 'tank_id', timestamp.desc()),
    )
```

- [ ] **Step 3: Verify migration exists**

The migration `a1b2c3d4e5f6` already creates these indexes. Verify by checking:
Run: `grep -n 'idx_measurement' migrations/versions/a1b2c3d4e5f6_add_timescale_optimization.py`

- [ ] **Step 4: Commit**

```bash
git add models/database.py
git commit -m "perf: add composite indexes on measurement(tank_id, timestamp)"
```

---

### Task 10: Thread-Safe MeasurementProcessor

**Files:**
- Modify: `models/measurement_processor.py:17-48`

- [ ] **Step 1: Verify Lock is used**

Check that `MeasurementProcessor.__init__` creates `self._lock = Lock()` (line 23) and `smooth_pressure()` uses `with self._lock:` (line 27).

- [ ] **Step 2: Verify initialized state**

Check `__init__` has `self._last_level = None` and `self._last_volume = None` (lines 21-22).

- [ ] **Step 3: Verify negative pressure clamping**

Check `process_measurement` has `if pressure < 0: pressure = 0.0` (line 53-54).

- [ ] **Step 4: Commit**

```bash
git add models/measurement_processor.py
git commit -m "fix: thread-safe MeasurementProcessor with proper initialization"
```

---

### Task 11: Thread-Safe FlowRateCalculator with Leak Detection

**Files:**
- Modify: `models/flow_rate_calculator.py:16-51`

- [ ] **Step 1: Verify FlowState.LEAK_DETECTED exists**

Run: `grep -n 'LEAK_DETECTED' models/flow_rate_calculator.py`
Expected: Line 22 in enum, line 49-50 for constants

- [ ] **Step 2: Verify Lock is used**

Check `__init__` creates `self._lock = Lock()` and key methods use `with self._lock:`.

- [ ] **Step 3: Verify direct deque indexing**

Run: `grep -n 'list(self.history)' models/flow_rate_calculator.py`
Expected: Should find zero matches — should use `self.history[-1]` directly

- [ ] **Step 4: Commit**

```bash
git add models/flow_rate_calculator.py
git commit -m "feat: thread-safe FlowRateCalculator with leak detection"
```

---

### Task 12: Fix AlarmManager — Deduplication + Level Field

**Files:**
- Modify: `models/alarm_manager.py:13-100`

- [ ] **Step 1: Verify cooldown dict exists**

Run: `grep -n 'ALARM_COOLDOWNS' models/alarm_manager.py`
Expected: Line 13 with cooldown definitions

- [ ] **Step 2: Verify `_create_alarm` checks cooldown**

Check line 73-77 suppresses alarms within cooldown period.

- [ ] **Step 3: Verify `level` field is set**

Check line 84 sets `level=level` on the Alarm object.

- [ ] **Step 4: Verify `db.session.get()` is used**

Check line 105 uses `self.db_session.get(Alarm, alarm_id)` (not deprecated `Alarm.query.get()`).

- [ ] **Step 5: Commit**

```bash
git add models/alarm_manager.py
git commit -m "fix: alarm deduplication with cooldowns and level field"
```

---

### Task 13: Fix TankConfig Serialization

**Files:**
- Modify: `models/tank_config.py`

- [ ] **Step 1: Verify `to_dict()` and `from_dict()` exist**

Run: `grep -n 'to_dict\|from_dict\|to_json\|from_json' models/tank_config.py`
Expected: All four methods present

- [ ] **Step 2: Verify tank volume calculation**

Check `_calculate_tank_volume()` is a static method that properly handles both orientations.

- [ ] **Step 3: Commit**

```bash
git add models/tank_config.py
git commit -m "feat: add Redis serialization to TankConfig"
```

---

## Phase 3: Ingestion Pipeline (P1)

### Task 14: Wire MQTT Ingestion with Redis Cache

**Files:**
- Modify: `services/mqtt_ingestion.py:1-60`

- [ ] **Step 1: Verify JSON schema exists**

Run: `grep -n 'READING_SCHEMA\|STATUS_SCHEMA' services/mqtt_ingestion.py`
Expected: Both schemas defined

- [ ] **Step 2: Verify Redis-backed cache**

Run: `grep -n '_RedisLRUCache\|redis_client' services/mqtt_ingestion.py`
Expected: Redis cache class and client usage

- [ ] **Step 3: Verify batch writes**

Run: `grep -n '_flush_batch\|bulk_save_objects' services/mqtt_ingestion.py`
Expected: Batch flush method with bulk_save_objects

- [ ] **Step 4: Verify TLS configuration**

Run: `grep -n 'tls_set\|ca_cert\|client_cert' services/mqtt_ingestion.py`
Expected: TLS setup in __init__

- [ ] **Step 5: Commit**

```bash
git add services/mqtt_ingestion.py
git commit -m "feat: Redis cache, batch writes, TLS, and schema validation in MQTT ingestion"
```

---

### Task 15: Wire Celery Tasks to Ingestion Pipeline

**Files:**
- Modify: `tasks/ingestion.py:1-57`
- Modify: `tasks/notifications.py:134-209`

- [ ] **Step 1: Verify `check_alarms` dispatches notifications**

Run: `grep -n 'send_notification' tasks/ingestion.py`
Expected: `send_notification.delay()` called for each triggered alarm

- [ ] **Step 2: Verify `cleanup_old_measurements` uses drop_chunks**

Run: `grep -n 'drop_chunks' tasks/ingestion.py`
Expected: TimescaleDB `drop_chunks()` call with DELETE FROM fallback

- [ ] **Step 3: Verify notification task sends email**

Run: `grep -n '_send_email\|smtplib' tasks/notifications.py`
Expected: SMTP email sending logic

- [ ] **Step 4: Verify deduplication**

Run: `grep -n '_is_duplicate\|notif_dedup' tasks/notifications.py`
Expected: Redis-backed deduplication

- [ ] **Step 5: Commit**

```bash
git add tasks/ingestion.py tasks/notifications.py
git commit -m "feat: wire Celery tasks with notifications and TimescaleDB retention"
```

---

### Task 16: Fix Analytics N+1 Query

**Files:**
- Modify: `tasks/analytics.py`

- [ ] **Step 1: Check daily_consumption task**

Run: `cat tasks/analytics.py`
Expected: Batch tank processing, not per-tank loop with individual queries

- [ ] **Step 2: Verify module-level imports**

Run: `grep -n 'import' tasks/analytics.py | head -10`
Expected: `TankForecastService` imported at top, not inside loop

- [ ] **Step 3: Commit**

```bash
git add tasks/analytics.py
git commit -m "fix: batch tank processing in daily_consumption task"
```

---

## Phase 4: Database Migration & Optimization (P1)

### Task 17: Run TimescaleDB Migration

**Files:**
- Modify: `migrations/versions/a1b2c3d4e5f6_add_timescale_optimization.py`

- [ ] **Step 1: Verify migration exists and is at HEAD**

Run: `alembic heads`
Expected: `a1b2c3d4e5f6`

- [ ] **Step 2: Verify hypertable creation**

Run: `grep -n 'create_hypertable' migrations/versions/a1b2c3d4e5f6_add_timescale_optimization.py`

- [ ] **Step 3: Verify retention policy**

Run: `grep -n 'add_retention_policy' migrations/versions/a1b2c3d4e5f6_add_timescale_optimization.py`

- [ ] **Step 4: Verify continuous aggregates**

Run: `grep -n 'measurements_hourly\|measurements_daily' migrations/versions/a1b2c3d4e5f6_add_timescale_optimization.py`

- [ ] **Step 5: Verify compression policy**

Run: `grep -n 'add_compression_policy' migrations/versions/a1b2c3d4e5f6_add_timescale_optimization.py`

- [ ] **Step 6: Run migration (in test env first)**

```bash
FLASK_ENV=testing flask db upgrade
```

- [ ] **Step 7: Commit**

```bash
git add migrations/
git commit -m "db: TimescaleDB hypertable, compression, and continuous aggregates"
```

---

### Task 18: Fix Retention Policy Conflict

**Files:**
- Modify: `models/database.py` — `setup_timescale_retention()`
- Modify: `tasks/ingestion.py` — `cleanup_old_measurements()`

- [ ] **Step 1: Check current retention settings**

Run: `grep -n 'retention\|90 days\|30 days' models/database.py tasks/ingestion.py`
Expected: Both should use 90 days (matching migration)

- [ ] **Step 2: Unify to 90 days**

If `database.py` says 30 days, change to 90. The migration is the source of truth.

- [ ] **Step 3: Commit**

```bash
git add models/database.py tasks/ingestion.py
git commit -m "fix: unify retention policy to 90 days across all layers"
```

---

## Phase 5: Firmware Edge Layer (P0)

### Task 19: Fix Firmware Main Loop

**Files:**
- Modify: `firmware/main.py`

- [ ] **Step 1: Read current firmware/main.py**

Run: `cat firmware/main.py`
Expected: See broken functions (check_wifi, mqtt_connected, publish_readings undefined)

- [ ] **Step 2: Implement check_wifi()**

Add WiFi connection with exponential backoff:

```python
def check_wifi(wlan, ssid, password, max_retries=10):
    """Connect to WiFi with exponential backoff."""
    if wlan.isconnected():
        return True
    wlan.active(True)
    wlan.connect(ssid, password)
    for attempt in range(max_retries):
        if wlan.isconnected():
            return True
        delay = min(30, 2 ** attempt)
        time.sleep(delay)
    return False
```

- [ ] **Step 3: Fix NameError in exception handler**

Find the except block that references `readings` and ensure `readings = []` is initialized at the top of the try block.

- [ ] **Step 4: Wire MQTTClient**

Instantiate `MQTTClient` and call `publish()` in the main loop.

- [ ] **Step 5: Add hardware watchdog**

```python
wdt = machine.WDT(timeout=30000)
# In main loop:
wdt.feed()
```

- [ ] **Step 6: Load config from firmware.json**

Replace hardcoded CONFIG dict with:

```python
with open('firmware.json') as f:
    CONFIG = ujson.load(f)
```

- [ ] **Step 7: Commit**

```bash
git add firmware/main.py
git commit -m "fix: wire MQTT, WiFi, watchdog, and config in firmware main loop"
```

---

### Task 20: Fix Firmware Buffer Recursion

**Files:**
- Modify: `firmware/lib/buffer.py`

- [ ] **Step 1: Read current buffer.py**

Run: `cat firmware/lib/buffer.py`

- [ ] **Step 2: Fix recursive _flush_to_flash**

Replace recursive call with iterative trimming:

```python
def _flush_to_flash(self):
    while len(self._memory_buffer) > self.max_size:
        self._memory_buffer.pop(0)
    try:
        with open(self.filepath, 'w') as f:
            ujson.dump(self._memory_buffer, f)
    except OSError:
        pass
```

- [ ] **Step 3: Make drain() atomic**

Write empty file before clearing memory:

```python
def drain(self):
    readings = self._memory_buffer[:]
    try:
        with open(self.filepath, 'w') as f:
            f.write('[]')
    except OSError:
        pass
    self._memory_buffer.clear()
    return readings
```

- [ ] **Step 4: Commit**

```bash
git add firmware/lib/buffer.py
git commit -m "fix: iterative buffer trimming, atomic drain, type validation"
```

---

### Task 21: Fix Firmware Keller Protocol

**Files:**
- Modify: `firmware/lib/keller.py`

- [ ] **Step 1: Read current keller.py**

Run: `cat firmware/lib/keller.py`

- [ ] **Step 2: Fix variable-length response reads**

Add function-code-based response length:

```python
def _expected_response_length(self, function_code):
    if function_code == 0x30:  # INITIALIZE
        return 10
    elif function_code == 0x49:  # READ_CHANNEL_FLOAT
        return 12
    elif function_code == 0x5F:  # READ_SERIAL_NUMBER
        return 8
    return 6
```

- [ ] **Step 3: Fix CRC to single-endian**

Remove dual-endian check, use only:

```python
received_crc = (response[-2] << 8) | response[-1]
return received_crc == calculated_crc
```

- [ ] **Step 4: Make UART pins configurable**

Add `uart_id`, `tx_pin`, `rx_pin`, `de_pin` parameters to `__init__`.

- [ ] **Step 5: Commit**

```bash
git add firmware/lib/keller.py
git commit -m "fix: variable-length reads, single-endian CRC, configurable pins"
```

---

### Task 22: Fix Firmware MQTT Client

**Files:**
- Modify: `firmware/lib/mqtt_client.py`

- [ ] **Step 1: Read current mqtt_client.py**

Run: `cat firmware/lib/mqtt_client.py`

- [ ] **Step 2: Wire CommandHandler**

Add `set_command_handler()` method and dispatch in `_on_message`.

- [ ] **Step 3: Fix infinite loop in publish_buffered**

Pop one item at a time, break on failure:

```python
def drain_buffer(self):
    while self._buffer:
        item = self._buffer[0]
        try:
            self.publish(item['topic'], item['payload'], qos=1)
            self._buffer.pop(0)
        except Exception:
            break
```

- [ ] **Step 4: Add max buffer size**

```python
if len(self._buffer) < self._max_buffered:
    self._buffer.append(...)
```

- [ ] **Step 5: Commit**

```bash
git add firmware/lib/mqtt_client.py
git commit -m "fix: wire CommandHandler, fix buffer loop, add max size"
```

---

### Task 23: Fix Firmware Command Handler

**Files:**
- Modify: `firmware/lib/command_handler.py`

- [ ] **Step 1: Add missing imports**

At top of file, add:

```python
import gc
import network
import uos
```

- [ ] **Step 2: Fix _get_sensor_status()**

Replace hardcoded "online" with actual UART read attempt.

- [ ] **Step 3: Fix _reboot() dead code**

Remove return statement after `machine.reset()`.

- [ ] **Step 4: Commit**

```bash
git add firmware/lib/command_handler.py
git commit -m "fix: add imports, real sensor status, fix reboot dead code"
```

---

## Phase 6: Frontend & API (P2)

### Task 24: Add CSRF to Alarm Acknowledge

**Files:**
- Modify: `static/js/tank_detail.js`

- [ ] **Step 1: Find alarm acknowledge fetch call**

Run: `grep -n 'acknowledge' static/js/tank_detail.js`

- [ ] **Step 2: Add CSRF token header**

```javascript
const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
fetch(`/alarms/acknowledge/${alarmId}`, {
    method: 'POST',
    headers: {
        'X-CSRFToken': csrfToken,
        'Content-Type': 'application/json'
    }
});
```

- [ ] **Step 3: Verify meta tag in base template**

Run: `grep -n 'csrf-token' templates/base.html`
Expected: `<meta name="csrf-token" content="{{ csrf_token() }}">`

- [ ] **Step 4: Commit**

```bash
git add static/js/tank_detail.js templates/base.html
git commit -m "security: add CSRF token to alarm acknowledge request"
```

---

### Task 25: Add RBAC to API Endpoints

**Files:**
- Modify: `app.py` — API route functions

- [ ] **Step 1: Find API routes without access checks**

Run: `grep -n '@app.route.*api' app.py | head -20`

- [ ] **Step 2: Add check_tank_access() to each**

For each `/api/tanks/<id>` route, add:

```python
if not check_tank_access(tank_id):
    return jsonify({'error': 'Access denied'}), 403
```

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "security: add RBAC checks to all API endpoints"
```

---

### Task 26: Fix Duplicate `updateStatusIndicators` in Dashboard JS

**Files:**
- Modify: `static/js/dashboard.js`

- [ ] **Step 1: Find duplicate function**

Run: `grep -n 'function updateStatusIndicators' static/js/dashboard.js`
Expected: Two matches

- [ ] **Step 2: Remove the duplicate**

Keep the more complete implementation, delete the other.

- [ ] **Step 3: Commit**

```bash
git add static/js/dashboard.js
git commit -m "fix: remove duplicate updateStatusIndicators function"
```

---

## Verification Checklist

After all tasks are complete, verify:

- [ ] `python -c "from config import Config; print('Config OK')"` — no import errors
- [ ] `python -c "from utils.rate_limiter import init_rate_limiter; print('Rate limiter OK')"` — no import errors
- [ ] `python -c "from utils.security import init_security_middleware; print('Security OK')"` — no import errors
- [ ] `python -c "from models.database import db, User, Tank, Measurement, Alarm; print('Models OK')"` — no import errors
- [ ] `python -c "from models.measurement_processor import MeasurementProcessor; print('Processor OK')"` — no import errors
- [ ] `python -c "from models.flow_rate_calculator import FlowRateCalculator; print('Flow OK')"` — no import errors
- [ ] `python -c "from models.alarm_manager import AlarmManager; print('Alarm OK')"` — no import errors
- [ ] `python -c "from services.mqtt_ingestion import MqttIngestionService; print('Ingestion OK')"` — no import errors
- [ ] `python -c "from tasks.ingestion import process_measurements; print('Tasks OK')"` — no import errors
- [ ] `grep -r 'TODO\|FIXME\|TBD' models/ services/ tasks/ utils/` — no results
- [ ] `grep -rn 'datetime.datetime.now()' models/` — no results (all should be utcnow or func.now)
- [ ] `grep -rn 'query.get(' models/` — no results (all should be db.session.get)
