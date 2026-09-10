# Production MQTT Ingestion Engine + Legacy Purge — Implementation Plan (SUB-1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete the legacy Flask-era root tree and extend the FastAPI ingestion engine to accept `fuel/{gateway_mac}/{readings,status}` topics via a Redis TTL tank cache, with idempotent inserts and broker-reconnect resilience.

**Architecture:** No rewrite — extend `platform/fmp/ingestion/main.py` (subscriptions + routing), add a `TankTtlCache`-style resolver in `platform/fmp/ingestion/cache.py`, convert `insert_measurements()` to `ON CONFLICT DO NOTHING`, and add reconnect/resubscribe + startup retry to the MQTT client lifecycle. Legacy deletion is a guarded atomic commit.

**Tech Stack:** Python 3.12, FastAPI, paho-mqtt, EMQX 5.8, Redis 7 (aioredis), SQLAlchemy 2 async + asyncpg, TimescaleDB, pytest + pytest-asyncio.

**Spec:** `platform/docs/superpowers/specs/2026-09-10-mqtt-ingestion-legacy-purge-design.md`

---

## Task 1: Guarded legacy tree deletion

Delete the legacy root files and directories, then verify nothing dangling remains. Work commit-by-commit but delete in one atomic commit.

**Files:**
- Delete (root): `app.py`, `admin.py`, `auth.py`, `k114_reader.py`, `test_k114_reader.py`, `config.py`, `celery_app.py`, `migrations.py`, `forms.py`, `i18n.py`, `custom_translations.py`, `setup_translations.py`, `tank_data_analysis.py`, `babel_conflict.cfg`, `babel_conflict.py`, `messages.pot`, `requirements.txt`, `tailwind.config.js`
- Delete (dirs): `blueprints/`, `models/`, `mqtt/`, `services/`, `tasks/`, `utils/`, `static/`, `templates/`, `translations/`, `migrations/`, `scripts/`, `firmware/`
- Touch: `docs/superpowers/plans/2026-09-10-modernization-README.md` → a short note that legacy was purged SUB-1, pointing to `platform/` as the only backend.

- [ ] **Step 1: Reference scan before deletion**

Run:
```bash
cd /home/ubuntu/fuel_monitoring
rg -n "from app import|from k114|k114_reader|import app$|from config import|from models\.|from services\.|from blueprints\.|import app\b" --glob '!docs/**' .
```
Expected: only hits inside `docs/superpowers/reports/` or `.worktrees/` (historical artifacts; not live code). `rg` exit code 1 with no matches is fine.

- [ ] **Step 2: Docker/nginx reference scan**

Run:
```bash
rg -n "app\.py|k114|celery_app|templates|./static|./models|./services|./mqtt" docker-compose.yml infra/ web/ platform/ 2>/dev/null
```
Expected: only `fmp.workers.celery_app` references in `docker-compose.yml` (platform-internal, keep). No root-file references.

- [ ] **Step 3: DB orphan-table scan**

Run:
```bash
docker compose exec -T db psql -U fuel_platform -d fuel_platform -c \
  "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name NOT IN ('measurements','station_totalizers','alembic_version','dispense_codes','allocations') ORDER BY 1;"
```
Expected: list of tables. Classify each — any legacy-only table (e.g. old `measurement`, legacy `tanks` duplicate, `device_config`, `k114_sessions`) is recorded for Task 2. If all remaining tables belong to the platform schema (tanks, sites, companies, stations, dispensers, fuel_types, users, notification_gateways, strapping_tables, etc.), record "no orphan tables".

- [ ] **Step 4: Write the purge README**

Create `docs/superpowers/plans/2026-09-10-modernization-README.md`:
```markdown
# Modernization — SUB-1

The legacy Flask-era monolith (repo root: `app.py`, `k114_reader.py`, `models/`,
`blueprints/`, `services/mqtt_ingestion.py`, `templates/`, `static/`, old SQLite
migration scripts) was purged in SUB-1 of the architectural modernization.

The production stack is now entirely under `platform/` (FastAPI, `fmp/` package)
and `web/` (React SPA). See `platform/docs/superpowers/specs/2026-09-10-mqtt-ingestion-legacy-purge-design.md`.
```

- [ ] **Step 5: Delete legacy files in one commit**

```bash
cd /home/ubuntu/fuel_monitoring
git rm -r app.py admin.py auth.py k114_reader.py test_k114_reader.py config.py \
  celery_app.py migrations.py forms.py i18n.py custom_translations.py \
  setup_translations.py tank_data_analysis.py babel_conflict.cfg babel_conflict.py \
  messages.pot requirements.txt tailwind.config.js \
  blueprints models mqtt services tasks utils static templates translations \
  migrations scripts firmware
git add docs/superpowers/plans/2026-09-10-modernization-README.md
git commit -m "refactor: purge legacy Flask root tree (SUB-1 modernization)"
```
Expected: commit removes the legacy tree atomically. If `git rm` errors on a missing file, note it and remove only existing paths (do not fail the commit).

- [ ] **Step 6: Post-deletion verification**

Run:
```bash
cd /home/ubuntu/fuel_monitoring && rtk docker compose ps
pytest -q platform/fmp/tests 2>&1 | tail -5
```
Expected: all containers still Up; pytest passes (118 tests, or new count from existing suite). This proves the platform never imported a deleted module.

## Task 2: Drop orphan DB tables (if any)

Only run if Task 1 Step 3 found legacy tables. Otherwise this entire task is skipped (mark checkboxes done with "no-op"). Work in `platform/alembic/versions/`.

**Files:**
- Create: `platform/alembic/versions/0002_drop_legacy_tables.py`
- Test: no unit test (schema-only migration)

- [ ] **Step 1: Scaffold the empty alembic revision**

Run:
```bash
cd /home/ubuntu/fuel_monitoring/platform && python -m alembic revision -m "drop legacy tables"
```
Open the generated file and replace the body of `upgrade()` and `downgrade()`:

```python
def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    legacy_tables = {"measurement", "device_config", "k114_sessions"}  # adjust to Step 3 findings
    for t in sorted(legacy_tables - set(inspector.get_table_names())):
        pass  # already gone
    for t in sorted(legacy_tables & set(inspector.get_table_names())):
        op.drop_table(t, if_exists=True)


def downgrade() -> None:
    # Legacy schema is not restored — data was synthetic/dev only.
    pass
```
Use `op.drop_table(t)` directly if the installed alembic/SQLAlchemy version has no `if_exists` on drop_table; wrap each in try/except if needed.

- [ ] **Step 2: Run the migration**

```bash
cd /home/ubuntu/fuel_monitoring/platform && python -m alembic upgrade head
```
Expected: prints upgrade to `0002`, no error.

- [ ] **Step 3: Verify + commit**

```bash
docker compose exec -T db psql -U fuel_platform -d fuel_platform -c \
  "SELECT table_name FROM information_schema.tables WHERE table_schema='public';"
git add alembic/versions/0002_drop_legacy_tables.py
git commit -m "chore: drop legacy orphan tables (SUB-1)"
```
Expected: legacy tables gone, platform tables intact.

## Task 3: TTL tank cache module

Create the cache that maps gateway_mac / sensor_serial → tank_id with positive (300s) and negative (60s) TTLs.

**Files:**
- Create: `platform/fmp/ingestion/cache.py`
- Test: `platform/fmp/tests/unit/test_ingestion_cache.py`

- [ ] **Step 1: Write the failing unit test**

Create `platform/fmp/tests/unit/test_ingestion_cache.py`:
```python
"""Unit tests: tank TTL cache + fuel-topic key helpers."""
from __future__ import annotations

import pytest

from fmp.ingestion.cache import (
    TANK_CACHE_TTL,
    TANK_NEG_TTL,
    neg_cache_key,
    resolve_tank_id,
    serial_cache_key,
    gateway_cache_key,
)
from fmp.tests.conftest import FakeRedis


async def test_key_helpers():
    assert serial_cache_key("SN-1") == "tank:by:serial:SN-1"
    assert gateway_cache_key("AA:BB") == "tank:by:gateway:AA:BB"
    assert neg_cache_key("SN-1") == "tank:neg:SN-1"


async def test_cache_ttl_constants():
    assert TANK_CACHE_TTL == 300
    assert TANK_NEG_TTL == 60


async def test_serial_hit_returns_tank_id():
    redis = FakeRedis(store={"tank:by:serial:SN-1": '"11111111-1111-1111-1111-111111111111"'})
    assert await resolve_tank_id(redis, sensor_serial="SN-1") == \
        "11111111-1111-1111-1111-111111111111"


async def test_negative_cache_returns_none():
    redis = FakeRedis(store={"tank:neg:SN-1": '"__NULL__"'})
    assert await resolve_tank_id(redis, sensor_serial="SN-1") is None


async def test_gateway_miss_returns_none():
    redis = FakeRedis()
    assert await resolve_tank_id(redis, gateway_mac="AA:BB") is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /home/ubuntu/fuel_monitoring/platform && python -m pytest fmp/tests/unit/test_ingestion_cache.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fmp.ingestion.cache'`.

- [ ] **Step 3: Implement the cache module**

Create `platform/fmp/ingestion/cache.py`:
```python
"""Tank resolution cache (MQTT topic/gateway → tank).

Speeds up `fuel/{gateway_mac}/readings` and legacy `ingestion/readings`
frames by caching tank_id behind gateway_mac / sensor_serial. DB lookups only
happen on cache miss; unknown devices get a short negative-cache entry so they
don't hot-loop the database.
"""
from __future__ import annotations

import json

TANK_CACHE_TTL = 300  # seconds
TANK_NEG_TTL = 60     # seconds
_NULL = "_NULL_"


def serial_cache_key(serial: str) -> str:
    return f"tank:by:serial:{serial}"


def gateway_cache_key(mac: str) -> str:
    return f"tank:by:gateway:{mac}"


def neg_cache_key(lookup: str) -> str:
    return f"tank:neg:{lookup}"


async def resolve_tank_id(redis, *, gateway_mac: str | None = None,
                          sensor_serial: str | None = None) -> str | None:
    """Return a tank_id cache value or None.

    Only reads the cache — the caller performs the DB upsert on miss.
    Precedence: gateway_mac first, then sensor_serial.
    """
    if gateway_mac:
        raw = await redis.get(gateway_cache_key(gateway_mac))
        lookup = gateway_mac
    elif sensor_serial:
        raw = await redis.get(serial_cache_key(sensor_serial))
        lookup = sensor_serial
    else:
        return None

    if raw is None:
        return None
    if raw == f'"{_NULL}"':
        # negative entry: resume after TANK_NEG_TTL
        await redis.get(neg_cache_key(lookup))
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def set_tank_cache(redis, *, tank_id: str,
                         gateway_mac: str | None = None,
                         sensor_serial: str | None = None) -> None:
    if gateway_mac:
        await redis.set(gateway_cache_key(gateway_mac), json.dumps(tank_id), ex=TANK_CACHE_TTL)
    if sensor_serial:
        await redis.set(serial_cache_key(sensor_serial), json.dumps(tank_id), ex=TANK_CACHE_TTL)


async def set_negative_cache(redis, *, lookup: str) -> None:
    await redis.set(neg_cache_key(lookup), json.dumps(_NULL), ex=TANK_NEG_TTL)
```
Note: `json.dumps(tank_id)` yields `'"<uuid>"'`, matching the unit test store values.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd /home/ubuntu/fuel_monitoring/platform && python -m pytest fmp/tests/unit/test_ingestion_cache.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add platform/fmp/ingestion/cache.py platform/fmp/tests/unit/test_ingestion_cache.py
git commit -m "feat: tank TTL cache for MQTT topic correlation (SUB-1)"
```

## Task 4: Idempotent measurement inserts

**Files:**
- Modify: `platform/fmp/ingestion/batch_writer.py`
- Test: `platform/fmp/tests/integration/test_telemetry_pipeline.py`

- [ ] **Step 1: Add the idempotency extension to the integration test**

In `platform/fmp/tests/integration/test_telemetry_pipeline.py`, at the end of `test_hypertables_and_pipeline` (after the `count == 2 + 8 + 5 + 20` assertion), add:
```python
    # --- idempotent re-inserts (ON CONFLICT DO NOTHING) -----------------
    async with async_session_factory() as session:
        dup = [
            {"timestamp": now, "tank_id": tank.id, "pressure": 0.5, "temperature": 20.0,
             "level": 1.0, "volume": 3141.0, "fill_percent": 34.1, "is_outlier": False, "status": 0},
        ]
        assert await insert_measurements(session, dup) == 1  # no exception
        await session.commit()
        count_after = (await session.execute(select(func.count()).select_from(Measurement))).scalar()
        assert count_after == 2 + 8 + 5 + 20  # unchanged
```
(`from fmp.ingestion.batch_writer import insert_measurements` already imported in that test.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /home/ubuntu/fuel_monitoring/platform && python -m pytest fmp/tests/integration/test_telemetry_pipeline.py -v`
Expected: FAIL — second insert of `now` raises `IntegrityError: duplicate key value`.

- [ ] **Step 3: Implement `ON CONFLICT DO NOTHING`**

Replace the body of `insert_measurements` in `platform/fmp/ingestion/batch_writer.py`:
```python
async def insert_measurements(session, rows: list[dict]) -> int:
    """Bulk-insert measurement rows; returns the number of rows requested.

    Duplicate (tank_id, timestamp) rows are silently skipped (ON CONFLICT DO
    NOTHING) so QoS-1 redelivered MQTT frames never raise on replay.
    """
    from sqlalchemy.dialects.postgresql import insert

    from fmp.models import Measurement

    if not rows:
        return 0
    stmt = insert(Measurement).on_conflict_do_nothing(
        index_elements=["tank_id", "timestamp"]
    )
    await session.execute(stmt, rows)
    return len(rows)
```
Note: `session.execute(stmt, rows)` with a list of dicts performs a multi-row insert; `on_conflict_do_nothing` needs the postgresql dialect `insert`, which is already imported.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd /home/ubuntu/fuel_monitoring/platform && python -m pytest fmp/tests/integration/test_telemetry_pipeline.py -v`
Expected: PASS — duplicate insert returns silently, count unchanged.

- [ ] **Step 5: Commit**

```bash
git add platform/fmp/ingestion/batch_writer.py platform/fmp/tests/integration/test_telemetry_pipeline.py
git commit -m "fix: idempotent measurement inserts via ON CONFLICT (SUB-1)"
```

## Task 5: Fuel-topic subscriptions + reconnect resilience in `main.py`

**Files:**
- Modify: `platform/fmp/ingestion/main.py`
- Test: `platform/fmp/tests/unit/test_fuel_topic_router.py` (new)

- [ ] **Step 1: Write the topic-router unit test**

Create `platform/fmp/tests/unit/test_fuel_topic_router.py`:
```python
"""Unit tests: fuel/{mac}/topic routing + payload frame handling."""
from __future__ import annotations

from fmp.ingestion.main import parse_fuel_topic


def test_parse_fuel_readings_topic():
    assert parse_fuel_topic("fuel/AA:BB:CC:DD:EE:01/readings") == ("AA:BB:CC:DD:EE:01", "readings", None)


def test_parse_fuel_status_topic():
    assert parse_fuel_topic("fuel/AA:BB:CC:DD:EE:01/status") == ("AA:BB:CC:DD:EE:01", "status", None)


def test_parse_non_fuel_topic_returns_none():
    assert parse_fuel_topic("ingestion/readings") is None
    assert parse_fuel_topic("fuel/readings") is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /home/ubuntu/fuel_monitoring/platform && python -m pytest fmp/tests/unit/test_fuel_topic_router.py -v`
Expected: FAIL with `ImportError: cannot import name 'parse_fuel_topic'`.

- [ ] **Step 3: Add `parse_fuel_topic` + subscriptions + reconnect handling**

In `platform/fmp/ingestion/main.py`:

3a. Add the topic parser above `_on_message`:
```python
def parse_fuel_topic(topic: str) -> tuple[str, str, None] | None:
    """Parse fuel/<gateway_mac>/<kind> → (gateway_mac, kind, None)."""
    parts = topic.split("/")
    if len(parts) == 3 and parts[0] == "fuel" and parts[2] in ("readings", "status"):
        return parts[1], parts[2], None
    return None
```

3b. In `lifespan()`: subscribe to 6 topics and add the `fuel/` routes to `_route()`, plus a resilient connect with retry loop. Replace the current connect/subscribe block:
```python
    _loop = asyncio.get_running_loop()
    _client = MqttClient(CallbackAPIVersion.VERSION2)
    _client.on_message = _on_message
    _client.connect_async(settings.MQTT_BROKER, settings.MQTT_PORT, settings.MQTT_KEEPALIVE)
    _client.loop_start()
    await _wait_connected(_client)
    _client.subscribe(
        [
            ("ingestion/readings", settings.MQTT_QOS),
            ("ingestion/status", settings.MQTT_QOS),
            ("ingestion/dispense/validate", settings.MQTT_QOS),
            ("ingestion/dispense/complete", settings.MQTT_QOS),
            ("fuel/+/readings", settings.MQTT_QOS),
            ("fuel/+/status", settings.MQTT_QOS),
        ]
    )
```
Add helper functions and the `on_connect` handler at module level:
```python
async def _wait_connected(client, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if client.is_connected():
            return
        await asyncio.sleep(0.2)
    raise ConnectionError("MQTT broker never became available")


def _on_connect(client, userdata, flags, reason_code, properties):
    client.subscribe(
        [
            ("ingestion/readings", settings.MQTT_QOS),
            ("ingestion/status", settings.MQTT_QOS),
            ("ingestion/dispense/validate", settings.MQTT_QOS),
            ("ingestion/dispense/complete", settings.MQTT_QOS),
            ("fuel/+/readings", settings.MQTT_QOS),
            ("fuel/+/status", settings.MQTT_QOS),
        ]
    )
```
and register it: after `_client.on_message = _on_message`, add `_client.on_connect = _on_connect`.

3c. In `_route(topic, payload)`, add the `fuel/` branch BEFORE the `ingestion/readings` check:
```python
        elif topic.startswith("fuel/"):
            parsed = parse_fuel_topic(topic)
            if parsed is None:
                logger.warning("dropped malformed fuel topic %s", topic)
                return
            gateway_mac, kind, _ = parsed
            if kind == "status":
                await _handle_status(redis, payload, gateway_mac)
            else:
                await _handle_reading(redis, payload, gateway_mac=gateway_mac)
```
Keep the existing `elif topic.startswith("ingestion/readings")` branch as-is (legacy compat).

3d. Update `_handle_reading` to accept `gateway_mac` and use the cache (imports added at top: `from fmp.ingestion.cache import resolve_tank_id, set_tank_cache, set_negative_cache`). Change the tank-resolution block from the float-tank lookup to:
```python
async def _handle_reading(redis, payload, *, gateway_mac: str | None = None) -> None:
    from datetime import datetime

    from fmp.models import Tank
    from fmp.ingestion.cache import resolve_tank_id, set_tank_cache, set_negative_cache

    sensor_serial = payload.get("sensor_serial") or payload.get("sensor_serial_number")
    tank_id = await resolve_tank_id(redis, gateway_mac=gateway_mac, sensor_serial=sensor_serial)

    async with async_session_factory() as session:
        tank_key = payload.get("tank_id")
        tank = None
        if tank_id is None and tank_key:
            tank_id = tank_key  # legacy payload may carry tank_id directly
        if tank_id:
            tank = await session.get(Tank, tank_id)
        if tank is None and not tank_id and sensor_serial:
            from sqlalchemy import select
            tank = (
                await session.execute(
                    select(Tank).where(Tank.sensor_serial_number == sensor_serial)
                )
            ).scalar_one_or_none()
        if tank is None and gateway_mac:
            from sqlalchemy import select
            tank = (
                await session.execute(
                    select(Tank).where(Tank.gateway_mac == gateway_mac)
                )
            ).scalar_one_or_none()
        if tank is None:
            if sensor_serial:
                await set_negative_cache(redis, lookup=sensor_serial)
            if gateway_mac:
                await set_negative_cache(redis, lookup=gateway_mac)
            logger.warning("no tank matched for reading on %s", getattr(payload, "topic", "?"))
            return
        if tank_id is None:
            await set_tank_cache(redis, tank_id=str(tank.id),
                                 gateway_mac=gateway_mac, sensor_serial=sensor_serial)

        frame = payload.get("measurement", payload)
        captured_at = frame.get("timestamp")
        ...  # unchanged from timestamp parsing onward
```
Remove the old `tank_key`/serial-only block. Keep `await session.commit()` and `publish_live` unchanged. (`session.get` triggers `selectin` for `fuel_type`, so `pipeline.process` keeps working.)

3e. Add `_handle_status`:
```python
async def _handle_status(redis, payload, gateway_mac: str) -> None:
    from datetime import datetime

    from fmp.models import Station, Tank

    async with async_session_factory() as session:
        tank = (
            await session.execute(select(Tank).where(Tank.gateway_mac == gateway_mac))
        ).scalar_one_or_none()
        if tank is None:
            logger.warning("no tank for gateway %s status frame", gateway_mac)
            return
        tank.connection_status = "online"
        tank.last_connection = datetime.now(timezone.utc)
        if tank.site_id:
            station = (await session.execute(select(Station).where(Station.id == tank.site_id))).scalar_one_or_none()
            if station is not None:
                station.last_heartbeat = datetime.now(timezone.utc)
        await session.commit()
        logger.info("heartbeat: gateway %s online (tank %s)", gateway_mac, tank.id)
```
Add needed imports at top of `main.py`: `from datetime import datetime, timezone`, `from sqlalchemy import select`, `import time`, and the `from fmp.ingestion.cache import ...` inside functions to keep import graph light (or at module top).

- [ ] **Step 4: Run the new unit test + full suite**

Run:
```bash
cd /home/ubuntu/fuel_monitoring/platform
python -m pytest fmp/tests/unit/test_fuel_topic_router.py fmp/tests/unit/test_ingestion_cache.py -v
python -m pytest fmp/tests -q 2>&1 | tail -3
```
Expected: new tests PASS; full suite green (118+ new tests).

- [ ] **Step 5: Syntax/import sanity**

Run: `python -c "from fmp.ingestion.main import app; print('ok')"`
Expected: `ok` — module imports cleanly (no MQTT connection at import time).

- [ ] **Step 6: Commit**

```bash
git add platform/fmp/ingestion/main.py platform/fmp/tests/unit/test_fuel_topic_router.py
git commit -m "feat: fuel/{mac}/readings+status MQTT topics, cache correlation, reconnect resubscribe (SUB-1)"
```

## Task 6: Integration + deployment verification

**Files:**
- No source code changes (verify only)

- [ ] **Step 1: Rebuild + redeploy the ingest container**

```bash
cd /home/ubuntu/fuel_monitoring && rtk docker compose up -d --build ingest emqx redis api
```
Expected: containers rebuilt, `ingest` logs `MQTT subscription active`.

- [ ] **Step 2: Confirm 6 active subscriptions**

Run:
```bash
rtk docker exec fuel-platform-emqx-1 emqx_ctl subscriptions list | rtk grep fuel
```
Expected:
```
fuel/+/readings ...
fuel/+/status ...
```

- [ ] **Step 3: E2E frame on the new topic (pressure in bar)**

Run (from `api` container):
```bash
rtk docker exec fuel-platform-api-1 python -c "
import paho.mqtt.client as mqtt, json
c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2); c.connect('emqx', 1883, 60)
c.publish('fuel/AA:BB:CC:DD:EE:01/readings', json.dumps({'sensor_serial':'SN-1001-01','pressure':0.133,'temperature':25.0,'status':0,'timestamp':'2026-09-10T03:00:00Z'}), qos=1)
c.disconnect(); print('published')
"
```
Expected: frame lands. Then:
```bash
cart=$(cd /home/ubuntu/fuel_monitoring && rtk docker compose ps -q api)
TOKEN=$(curl -s -X POST http://localhost/api/v1/auth/login -H 'Content-Type: application/json' -d '{"username":"admin","password":"admin123"}' | jq -r .access_token)
curl -s "http://localhost/api/v1/tanks/a519f5bc-6ca8-4a46-bfa9-bcc5d57359ea/recent" -H "Authorization: Bearer $TOKEN" | jq -c '.[-1] | {timestamp, level, fill_percent}'
```
Expected: last reading is the new frame (level ≈1.826, fill ∝ 76).

- [ ] **Step 4: Redis cache warm**

Run:
```bash
rtk docker exec fuel-platform-redis-1 redis-cli TTL tank:by:gateway:AA:BB:CC:DD:EE:01
```
Expected: TTL ≤ 300 and ≥ 0 (cache populated). 

- [ ] **Step 5: Heartbeat test**

Run:
```bash
rtk docker exec fuel-platform-api-1 python -c "
import paho.mqtt.client as mqtt, json
c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2); c.connect('emqx', 1883, 60)
c.publish('fuel/AA:BB:CC:DD:EE:01/status', json.dumps({'status':'online'}), qos=1)
c.disconnect(); print('status published')
"
```
Then verify the tank's `connection_status == 'online'` via the API tanks list (first tank in `/api/v1/tanks` `connection_status`).

- [ ] **Step 6: Full regression + clean logs**

Run:
```bash
cd /home/ubuntu/fuel_monitoring && rtk docker compose ps
rtk docker logs --tail=20 fuel-platform-ingest-1
```
Expected: all containers Up; ingest logs show no new tracebacks (the idempotent insert path means no `IntegrityError` on replay, and the 21:50-era duplicate frame logs cease).

- [ ] **Step 7: Commit any incidental fixes (none expected)**

If anything had to be adjusted during verification (e.g. a type in the new module), commit it as `fix: <what>`; otherwise skip.

---

## Exit Criteria (from spec)

- [ ] Legacy tree gone; `docker compose ps` clean.
- [ ] 6 MQTT subscriptions active (`ingestion/*` ×4 + `fuel/+/×2`).
- [ ] `fuel/{mac}/readings` frame lands in TimescaleDB; `tank:by:gateway` key warm.
- [ ] Duplicate (tank_id, timestamp) inserts are silent.
- [ ] Full backend suite green; web untouched.