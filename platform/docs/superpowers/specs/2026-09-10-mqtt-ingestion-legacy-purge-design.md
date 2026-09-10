# Production MQTT Ingestion Engine + Legacy Purge — Design Spec (SUB-1)

Date: 2026-09-10
Status: Approved (design review of 2026-09-10)
Branch: main
Project: Architectural modernization — Sub-project 1 of 3

## Purpose

Modernize the fuel-monitoring platform to a pure-MQTT data plane and remove all
legacy Flask-era code. SUB-1 delivers two sides of the modernization:

1. **Delete the legacy root tree** so `platform/` + `web/` become the single source
   of truth.
2. **Extend the production ingestion engine** (`platform/fmp/ingestion/`) to accept
   the gateway-centric `fuel/{gateway_mac}/{readings,status}` topics alongside the
   existing `ingestion/*` topics, resolving tanks through a Redis TTL cache, plus
   production hardening identified during smoke testing.

Follow-up sub-projects (NOT in scope here): SUB-2 IoT gateway command API, SUB-3
frontend overhaul (dark mode, 3D gauge, gateway console).

## Approach

Extend the existing FastAPI ingestion service; do not rewrite it. Keep the current
`ingestion/*` topics working for backward compat. Add `fuel/+` subscriptions and a
per-frame tank resolution cache. Fold in three production-hardening fixes discovered
during E2E smoke testing (idempotent inserts, broker startup resilience, reconnect
resubscribe). Legacy deletion is a guarded atomic commit — no live reference may
dangle.

---

## 1. Legacy code removal

Delete the Flask-era tree at the repo root so it can never be imported by the
production stack:

- `app.py`, `k114_reader.py`, `test_k114_reader.py`, `config.py`, `celery_app.py`,
  `migrations.py`, `form.py`/`forms.py`, `i18n.py` (and any other top-level legacy
  `.py` — enumerated at removal time by directory scan).
- `services/` (includes `mqtt_ingestion.py`), `models/`, `blueprints/`, `mqtt/`,
  `tasks/`, `utils/`, `templates/`, `static/`.

### Guard rails (must pass before/at deletion)

1. **Import scan**: `grep -rn` for imports of any legacy module across `platform/`,
   `web/`, `docker-compose.yml`, `nginx/`, `docker/`, `Makefile`. Any hits are
   resolved (manually removed) in the same commit.
2. **DB table scan**: query information_schema for orphan tables created only by the
   legacy app (e.g. `measurement`, legacy device/`tanks` tables distinct from the
   platform schema). If found, drop them via one dedicated empty alembic revision
   (`down_revision` chained), not raw SQL. Platform tables remain untouched.
3. **Docker/volume scan**: remove any legacy service/volume references in
   `docker-compose.yml` so `docker compose up` stays clean afterwards.
4. `.env*` and local config files are gitignored and left alone.

## 2. MQTT ingestion engine (`fuel/+/` topics)

### 2.1 Subscriptions (`fmp/ingestion/main.py`)

Add to the boot-time `_client.subscribe(...)` list (QoS from `settings.MQTT_QOS`):

- `fuel/+/readings` — tank sensor frames
- `fuel/+/status` — gateway heartbeats

Existing subscriptions remain unchanged: `ingestion/readings`, `ingestion/status`,
`ingestion/dispense/validate`, `ingestion/dispense/complete`.

### 2.2 Topic → tank correlation (Redis TTL cache)

Today every frame does a DB `SELECT` on `Tank.sensor_serial_number`. Replace with a
Redis TTL cache (new, in `fmp/ingestion/cache.py`):

- Key `tank:by:gateway:{mac}` → `{"tank_id": "<uuid>"}`, TTL 300 s.
- Key `tank:by:serial:{serial}` → `{"tank_id": "<uuid>"}`, TTL 300 s.
- DB miss → negative cache key `tank:neg:{lookup}` = `"__NULL__"`, TTL 60 s, so
  unknown devices do not hot-loop the DB.
- Lookup precedence for a `fuel/{mac}/readings` frame:
  1. gateway_mac from the topic → `tank:by:gateway` cache; miss → DB by
     `Tank.gateway_mac`.
  2. else `sensor_serial` / `sensor_serial_number` payload field → `tank:by:serial`
     cache; miss → DB by `Tank.sensor_serial_number`.
  3. else drop frame with a cache negative entry.
- `ingestion/readings` frames (no gateway in topic) keep the existing payload-based
  lookup path, now also cache-backed.
- Invalidation is lazy via TTL (300 s); a later sub-project can add an event bus.

### 2.3 `fuel/{mac}/status` heartbeats

Parse `fuel/{gateway_mac}/status`; resolve the tank via the same gateway cache/DB
path, then update the owning station's `Station.last_heartbeat` (the field used by
the dashboard/online signal) to the frame timestamp. Frames for unknown gateways are
logged and skip the heartbeat write — no new tables in SUB-1. SUB-2 adds the full
`IoTGateway` model with its own `last_seen`.

### 2.4 Payload contract (unchanged from ingestion/readings)

`fuel/{mac}/readings` frames carry the same JSON the platform already ingests:
`{ "sensor_serial": "...", "pressure": <bar>, "temperature": <°C>, "status": 0,
"timestamp": "<ISO8601>" }`. Pressure remains **bar** (per E2E smoke test finding;
`processor.py:pressure_to_level` demands bar).

## 3. Production hardening (from smoke test)

1. **Idempotent measurement inserts** — `insert_measurements()` becomes
   `INSERT ... ON CONFLICT (tank_id, timestamp) DO NOTHING` so QoS-1 redelivered
   frames with duplicate PKs are dropped silently instead of logging tracebacks
   (observed repeatedly during E2E).
2. **Broker startup resilience** — in `lifespan()`, retry `_client.connect()` with
   bounded backoff (e.g. 2 s → 30 s, max ~5 attempts) so the service starts even if
   EMQX is briefly unavailable (observed: `Application startup failed` after restarts).
3. **Reconnect resubscribe** — register an `on_connect` callback that re-issues the
   6-topic subscription on every (re)connect. Observed: after an EMQX restart the
   client reconnected with `subscriptions=0` and never re-subscribed.

## 4. Testing

- **Unit** (`fmp/tests/unit/test_ingestion_cache.py`):
  - `fuel/{mac}/readings` topic → gateway_mac extraction.
  - Cache hit path (no DB query), cache miss → DB populate, negative-cache path.
  - `insert_measurements` idempotency: inserting the same (tank_id, timestamp) twice
    returns silently on the second call, no exception.
- **Integration** (`fmp/tests/integration/test_fuel_topic_ingestion.py`): publish
  `fuel/{mac}/readings` + `fuel/{mac}/status` against the live EMQX broadcast loop → a
  measurement row is written and the tank cache is warm.
- **Regression**: all 118 existing backend tests remain green; `web` untouched in SUB-1.

## 5. Verification

- `pytest` full backend suite.
- Rebuild + redeploy `ingest` container.
- Republish the earlier smoke frame on `fuel/SN-1001-01/readings` (pressure in bar) →
  confirm a new TimescaleDB row and a warm `tank:by:gateway` key after the first frame.
- `docker compose ps` and `web`/`api` logs clean after the legacy deletion.

## 6. Sequencing & exit criteria

Single implementation plan. Order: (1) legacy removal with guards, (2) cache module +
topic parsing, (3) hardening, (4) tests, (5) verify + redeploy, (6) commit.
Exit criteria: legacy tree gone, 6-topic subscription active, idempotent ingest, all
tests green, live smoke frame lands end-to-end.