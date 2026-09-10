# IoT Gateway Command API — Design Spec (SUB-2)

Date: 2026-09-11
Status: Approved (design review of 2026-09-11)
Branch: main
Project: Architectural modernization — Sub-project 2 of 3

## Purpose

Add a managed `IoTGateway` entity and a command API that lets operators send
control commands to edge gateways over MQTT, with durable relay, correlated
acknowledgements, retries, and a full history/audit trail. SUB-2 is the
"command plane" complement to SUB-1's ingestion plane, and precedes SUB-3's
frontend overhaul (dark mode, 3D gauge, gateway console).

SUB-1 (merged 2026-09-10) established the `fuel/{gateway_mac}/{readings,status}`
topics and deferred this work: *"SUB-2 adds the full `IoTGateway` model with its
own `last_seen`."*

## Scope

In scope:
- New `iot_gateways` and `gateway_commands` tables (+ `tanks.gateway_id` FK).
- Gateway provisioning: auto-create on first-seen heartbeat, admin linking.
- Command API on the main API service (port 8000) with role-guarded auth.
- Durable Redis-list relay to the ingestion service (port 8001).
- MQTT command publish (`fuel/{mac}/command`) + ack consumption
  (`fuel/{mac}/command/ack`).
- Command state machine with Celery-beat TTL sweeper and retries.
- Full frontend gateway console (list, detail, command composer, history).

Out of scope:
- Firmware-side implementation of command handlers (gateway device behavior).
- Replacing the legacy `tank.gateway_mac` correlation (ingestion keeps using it).
- Notification-gateway console (existing `/admin/gateways` is unchanged).
- SUB-3 visual overhaul.

## Command catalog

| type            | purpose                                   | payload (required)        |
|-----------------|-------------------------------------------|---------------------------|
| `reboot`        | restart the gateway                       | —                         |
| `status_probe`  | publish a status frame now                | —                         |
| `pause_reporting` | stop periodic readings                  | `duration_s` (optional)   |
| `resume_reporting` | resume periodic readings                | —                         |
| `set_interval`  | change periodic reading cadence           | `interval_s` (int, ≥1)    |
| `recalibrate`   | re-zero a sensor against a reference      | `sensor` (str), `reference_pressure_bar` (float) |
| `zero_tank`     | reset tank level to zero                  | `tank_serial` (str), optional `level_m` (float) |
| `push_config`   | push arbitrary config JSON                | free-form JSON object     |

## Architecture

Three services collaborate:

```
Admin console (web/) ──HTTP──> API (8000, fmp/api)
                                 │   POST commands → row (pending) + LPUSH outbound
                                 ▼
                              Redis list  iot:commands:outbound
                                 │   BRPOPLPUSH → inflight
                                 ▼
                              Ingestion (8001, fmp/ingestion main loop)
                                 │   publish MQTT fuel/{mac}/command (QoS 1)
                                 ▼
                              EMQX ──> gateway ... gateway ──> EMQX
                                 │   ack fuel/{mac}/command/ack
                                 ▼
                              Ingestion on_message → update row → acked/rejected
                                 │
                          Celery beat TTL sweeper ──> retry / fail (DB scan)
```

### 4.1 Data model

**`iot_gateways`** (new)

| column             | type               | notes                                   |
|--------------------|--------------------|-----------------------------------------|
| `id`               | uuid PK            | UUIDPrimaryKeyMixin                     |
| `gateway_mac`      | String(17) unique  | indexed; matches `fuel/{mac}/...`       |
| `name`             | String(100)        | admin-assigned; default = MAC           |
| `firmware_version` | String(32) null    | from status heartbeat if present        |
| `last_seen`        | DateTime(tz) null  | refreshed on heartbeat and ack          |
| `connection_status`| String(20)         | `online`/`offline`, default `offline`   |
| `is_active`        | Boolean            | default False; True once admin links    |
| timestamps         | —                  | TimestampMixin                          |

**`tanks`** (change)

| column      | type    | notes                                            |
|-------------|---------|--------------------------------------------------|
| `gateway_id`| uuid FK | nullable → `iot_gateways.id`; backfilled from `gateway_mac` |

`tank.gateway_mac` is retained as the live correlation key for SUB-1 ingestion;
it is not migrated away in SUB-2.

**`gateway_commands`** (new)

| column             | type               | notes                                    |
|--------------------|--------------------|------------------------------------------|
| `id`               | uuid PK            |                                          |
| `gateway_id`       | uuid FK            | → `iot_gateways.id`, indexed             |
| `command_id`       | uuid               | unique; sent to gateway for correlation  |
| `command_type`     | String(32)         | one of the catalog verbs                  |
| `payload_json`     | JSONB              | validated payload; `{}` for none         |
| `status`           | String(20)         | pending/sent/acked/rejected/failed       |
| `attempts`         | Integer            | default 0                                |
| `max_attempts`     | Integer            | default 3                                |
| `sent_at`          | DateTime(tz) null  | last relay into MQTT                     |
| `next_retry_at`    | DateTime(tz) null  | sweeper gate                             |
| `ack_status`       | String(32) null    | `executed`/`rejected` from ack frame     |
| `ack_detail`       | String(255) null   | free text from ack/reject frame          |
| `ack_received_at`  | DateTime(tz) null  |                                          |
| `error_message`    | String(255) null   | on failure                               |
| timestamps         | —                  | TimestampMixin                           |

### 4.2 Schema/migration strategy

Schema is created by `fmp/scripts/init_db.py` (`Base.metadata.create_all`,
checkfirst — idempotent, matches SUB-1). Because create_all will not add the
new `tanks.gateway_id` column to an existing table, SUB-2 ships a standalone
one-shot backfill script `fmp/scripts/backfill_gateways.py` that:
1. `ALTER TABLE tanks ADD COLUMN IF NOT EXISTS gateway_id UUID` referencing
   `iot_gateways(id)`, plus index.
2. Upserts `iot_gateways` rows from distinct existing `tank.gateway_mac` values.
3. Sets `tanks.gateway_id` from matching `iot_gateways.gateway_mac`.
4. Runs before the ingestion/API services start (compose `db-init` step).

No alembic reintroduction (alembic is unused at runtime; SUB-1 verified no
`alembic_version` table).

## Command flow

1. Admin `POST /api/v1/iot-gateways/{id}/commands` with `{command_type, payload}`.
2. API validates payload against the command catalog, inserts `gateway_commands`
   row (`status=pending`, fresh `command_id`), LPUSHes
   `{command_id, gateway_mac, type, payload, issued_at}` to
   `iot:commands:outbound`. Returns `{command_id, status: "pending"}` — async accept.
3. Ingestion relay task: `BRPOPLPUSH outbound → inflight`; on MQTT `publish`
   success, LPOP inflight; updates row `status=sent`, `sent_at`, `attempts+=1`,
   `next_retry_at = now + backoff_interval`.
4. Gateway executes, publishes ack `{command_id, status, detail?}` to
   `fuel/{mac}/command/ack` (QoS 1).
5. Ingestion `_on_message` route → ack handler: match row by `command_id`;
   set `status=acked`/`rejected`, `ack_status`, `ack_detail`, `ack_received_at`;
   refresh gateway `last_seen`, set `connection_status=online`.
6. Celery beat sweeper (recurring, e.g. every 30–60 s) scans
   `status='sent' AND next_retry_at < now`:
   - `attempts < max_attempts` → re-LPUSH to outbound, `sent_at`/`attempts`
     bumped by relay on next publish.
   - else → `status='failed'`, `error_message='max attempts (retry) exhausted'`.
   Also flags `status='pending' AND created_at < now - pending_ttl` (ingestion
   never picked it up) → failed.

### 5.1 Backoff

Exponential: `60s * 2^(attempts-1)` capped at 15 min, configurable via
`COMMAND_BACKOFF_BASE_SECONDS` (env, default 60). `pending_ttl` default 120 s.
`max_attempts` constant at 3 for all commands in SUB-2 (enforced at the API
layer; no per-command override).

## MQTT contract

- **Command frame** → `fuel/{gateway_mac}/command` QoS 1:
  `{"command_id": "<uuid>", "type": "<verb>", "payload": {...}, "issued_at": "<ISO8601>", "attempts": N}`
- **Ack frame** → `fuel/{gateway_mac}/command/ack` QoS 1:
  `{"command_id": "<uuid>", "status": "executed"|"rejected", "detail": "<optional text>"}`
- Ingestion subscribes `fuel/+/command/ack` (one additional wildcard sub; the
  `fuel/+/...` pattern does not collide with the 6 existing subs).
- Unknown ack `command_id` → logged, ignored (no row churn).
- Ack for an inactive gateway → still logged/recorded if the row exists.

## API surface (port 8000, under `fmp/api/v1/iot_gateways.py`)

All routes registered via `app.include_router()` in `fmp/api/main.py`.

| method | path                                          | auth (view)                       |
|--------|-----------------------------------------------|-----------------------------------|
| POST   | `/api/v1/iot-gateways`                        | admin create                      |
| GET    | `/api/v1/iot-gateways`                        | any authed — list                 |
| GET    | `/api/v1/iot-gateways/{id}`                   | any authed — detail + linked tanks|
| PATCH  | `/api/v1/iot-gateways/{id}`                   | admin (rename/link/toggle active) |
| POST   | `/api/v1/iot-gateways/{id}/commands`          | admin send command                |
| GET    | `/api/v1/iot-gateways/{id}/commands`          | any authed — history (paginated, status filter) |

Auth guard: `require_roles("admin")` for writes; `CurrentUser` for reads.
Company scope: gateways are global until SUB-3; company_admin is NOT granted
command rights in SUB-2 (matches the chosen "admin send, auth view" model).

## Provisioning detail

- On `fuel/{mac}/status` heartbeat for a MAC with no `iot_gateways` row:
  ingestion auto-creates one with `is_active=False`,
  `connection_status='online'`, `last_seen=now`, `firmware_version` from frame
  (field `firmware_version` if present). Logged as `gateway auto-registered`.
- A tank still correlated by `gateway_mac`; admin links by PATCH (add/remove
  `tank_ids`, which sets `is_active=True` when first tank linked).
- Auto-created rows are listed in the console with an "unprovisioned" badge and
  no command composer until active.

## Frontend console (web/)

- New route `/admin/iot-gateways` + nav entry "IoT Gateways" (distinct from the
  notification "Gateways" → `/admin/gateways`).
- **List page:** table (name, MAC, status pill, last_seen, firmware, tanks,
  active) + "New gateway" admin action.
- **Detail page:**
  - Summary card: status, last_seen, firmware, active toggle (admin).
  - Linked tanks panel (unchanged tank data).
  - Command composer (admin): type dropdown → dynamic payload form
    (set_interval → `interval_s`; recalibrate → sensor + reference_pressure_bar;
    zero_tank → tank_serial/level_m; push_config → JSON textarea). Submit shows
    returned `command_id`.
  - History timeline: status chips, attempts, ack/reject info, timestamps.
  - Unprovisioned gateways show no composer.
- New API client module `web/src/api/iot.ts` + types in `web/src/lib/apiTypes.ts`.
  Polling refresh (no SSE in SUB-2; SUB-3 may add live push).
- Follow existing frontend conventions (query client, role-gated controls).

## Error handling

| condition                          | behavior                                |
|------------------------------------|-----------------------------------------|
| unknown gateway on command POST    | 404                                     |
| invalid payload for command type   | 422 (pydantic per-type validators)      |
| Redis relay unavailable            | 503; row left `pending` (sweeper TTL)   |
| unauthorized send/view              | 401/403 via existing deps               |
| MQTT publish failure at relay      | row stays `pending`; sweeper retries    |
| ack for unknown `command_id`       | log + ignore                            |

## Testing

- **Unit (fmp/tests/unit):**
  - payload validator per command type (accept/reject table).
  - relay enqueue/dequeue round-trip against FakeRedis.
  - ack-frame parsing + row transition helpers.
  - sweeper selection query + backoff computation.
- **Integration (fmp/tests/integration):**
  - Full loop: POST command → pending row → pop relay → publish (capture via
    paho `on_publish`/message-spy) → simulate ack → row acked; gateway
    `last_seen`/`connection_status` updated.
  - Retry: forced publish failure → sweeper republish → exhausted → failed.
  - Provisioning: heartbeat auto-creates inactive row; PATCH link activates.
  - Tanks backfill script: pre-existing `gateway_mac` values → `gateway_id`.
  - Existing integration pattern: `drop_all`/`create_all` at start.
- **Frontend:** vitest + React Testing Library with mocked API client for
  list/detail/composer/history and role gating (existing conventions).

## Success criteria

1. Admin can send all 8 command types via API or console; payloads validated.
2. Commands survive an ingestion restart (queued in Redis, not lost).
3. Ack/reject from gateway reflected in history with attempt/backoff tracking;
   unacked commands auto-fail after `max_attempts`.
4. Unknown gateway heartbeats are auto-registered (inactive) and never crash
   ingestion.
5. `fuel/{mac}/status` still updates tank + owning station (`Station.site_id` —
   SUB-1 fix regression-safe).
6. Existing suite (127 tests) stays green; SUB-2 adds its own tests.
7. Console renders list/detail/composer/history; command send works end-to-end
   in a live compose run against EMQX + Redis + Postgres.