# Legacy (Flask) vs Current (FastAPI) Feature Parity Audit

**Date:** 2026-09-11
**Auditor:** opencode (fuel_monitoring repo)
**Status:** DRAFT — gaps (a)–(e) require either implementation or explicit user sign-off

## 1. Scope & Method

The legacy Flood-Tank/measurement platform (Flask, deployed before this codebase
was rewritten to FastAPI + TimescaleDB + React) is described only by archived
reports in `docs/archive/legacy-flask/`. No legacy source tree survives in this
repo (the deleted worktrees `frontend-completion` and `fuel-dynamics-scada`
referenced an ESP32-S3 + Keller K114 edge, MQTT TLS ingestion, and Flask
dashboards). This audit therefore compares the capabilities the legacy reports
*describe* against what the current platform *actually implements*, citing
current `file:line` evidence. Every claim below was verified by direct grep/read,
never assumed.

Legacy reference documents:
- `docs/archive/legacy-flask/01_system_health_architecture_report.md`
- `docs/archive/legacy-flask/03_database_migration_script.md`
- `docs/archive/legacy-flask/04_scale_deployment_roadmap.md`
- `docs/archive/legacy-flask/05_expanded_full_layer_refactor.md`

## 2. Verdict legend

| Verdict | Meaning |
|---|---|
| `MIGRATED` | Fully present in current code; citation given |
| `PARTIAL` | Present but with a meaningful gap vs. legacy behavior |
| `DROPPED` | Not present anywhere in current code (verified by grep); parity gap |
| `IMPROVED` | Present and deliberately better than legacy (legacy had a root-cause bug) |

## 3. Capability matrix

### 3.1 Ingestion & processing

| Capability (legacy) | Verdict | Current evidence |
|---|---|---|
| MQTT ingestion (EMQX broker, encrypted TLS) | `MIGRATED` | `fmp/ingestion/main.py:56-72` (Paho client, `fuel/+/readings` + `ingestion/readings`); EMQX service in `docker-compose.yml` |
| JSON schema validation at broker | `PARTIAL` | Frames validated structurally in handlers, but no JSON-Schema/docstring contract; malformed topics dropped at `main.py:125-132, 150-166` |
| `MeasurementProcessor` pressure→level→volume→fill%→nsv | `MIGRATED` | `fmp/ingestion/pipeline.py:139-177` + `fmp/ingestion/processor.py` (EMA, MAD outlier, `pressure_to_level`, `calculate_volume`, `net_standard_volume`) |
| AlarmManager: thresholds + open-state dedup/cooldown | `MIGRATED` | `pipeline.py:60-94` (`evaluate_alarm_rules`), `97-98` open-alarm Redis key, `183-198` fires once while open |
| FlowRateCalculator | `DROPPED` | No flow-rate computation exists; `measurements` has no flow_rate column |
| Per-tank Redis cache + negative cache for unknown devices | `MIGRATED` | `fmp/ingestion/cache.py` (used in `main.py:177-222`) |
| Batch writes to TimescaleDB hypertable | `MIGRATED` | `fmp/ingestion/batch_writer.py` `insert_measurements`; `ensure_hypertables` on startup (`main.py:47-53`) |
| Offline edge re-buffer / backfill endpoint | `MIGRATED` | `POST /api/v1/ingest/backfill` `main.py:334-346` |
| Heartbeat/status auto-register gateways | `MIGRATED` | `_handle_status` `main.py:248-290` |

### 3.2 TimescaleDB lifecycle (→ high-priority items a, b, c)

| Capability (legacy) | Verdict | Current evidence |
|---|---|---|
| Hypertable for measurements + station totalizers | `MIGRATED` | `fmp/ingestion/batch_writer.py` `ensure_hypertables` |
| 30-day retention policy | `DROPPED` | **No** `add_retention_policy`/`drop_chunks` anywhere (grep: 0 hits in `platform/fmp`). Data grows unbounded. → **item (c)** |
| Continuous aggregates (hourly/daily) | `DROPPED` | **No** `CREATE MATERIALIZED VIEW`/`add_continuous_aggregate_policy` (grep: 0 hits). Dashboard only does ad-hoc `func.time_bucket` — see §4(a). |
| Continuous aggregate **refresh policy** | `DROPPED` (legacy was also broken) | Legacy report 01 flagged creator-as-written has *no* refresh policy; legacy 03 fixed it. Current has neither. → **item (a)** |
| Compression policy (≈80% space) | `DROPPED` (legacy not configured) | **No** `add_compression_policy` (grep: 0 hits). Legacy itself had none (report 01 §“No compression policy”). → **item (b)** |
| `cleanup_old_measurements` (`drop_chunks`) Celery task | `DROPPED` | No such task. → **item (c)** |

### 3.3 Analytics / export (→ high-priority items d, e)

| Capability (legacy) | Verdict | Current evidence |
|---|---|---|
| `tasks/analytics.py` daily consumption + forecast | `DROPPED` | Only Celery tasks are `notifications.*` and `commands.sweep_commands` (`fmp/workers/tasks/`); beat schedule is `sweep-gateway-commands` only (`fmp/workers/celery_app.py`). → **item (d)** |
| `tasks/export.py` streamed CSV (date-range, 1000-row batches) | `DROPPED` | `csv` module only used for *reading* uploads (`fmp/services/dispensing/excel_ingestion.py`). No download/export endpoint. → **item (e)** |

### 3.4 Dispensing, notifications, users (current-only surface)

These capabilities are new in the current platform and have no legacy equivalent
(report 01 predates the dispensing engine). Included for completeness.

| Capability | Evidence |
|---|---|
| Code validation + dispense completion | `fmp/services/dispensing/dispense_engine.py`, endpoints `fmp/api/v1/dispensing.py` |
| Upload batch / Excel ingestion | `fmp/services/dispensing/excel_ingestion.py` |
| Dispensing + fuel dynamics CRUD (fuel_types, strapping_tables) | `fmp/api/v1/{dispensing,fuel_types,strapping}.py`; `fmp/models/fuel.py` |
| JWT auth, RBAC (`CurrentUser`/`PrivilegedUser`/`require_roles`) | `fmp/api/deps.py` |
| Notification dispatch (SMS/WhatsApp codes, batch) | `fmp/workers/tasks/notifications.py`; API `fmp/api/v1/notifications.py` |
| IoT gateway command relay (durable queue, backoff, sweeper, acks) | `fmp/ingestion/relay.py`; `fmp/workers/tasks/commands.py`; `fmp/api/v1/iot_gateways.py` |

### 3.5 API & realtime

| Capability (legacy) | Verdict | Current evidence |
|---|---|---|
| Telemetry SSE / live updates | `MIGRATED` (now WebSocket) | `fmp/api/v1/realtime.py` `/ws/telemetry`, `/ws/alarms`; `fmp/api/realtime.py` `manager` |
| Recent readings (last N) | `MIGRATED` | `fmp/api/v1/tanks.py` `/recent`; frontend `web/src/hooks/useTelemetry.ts:11` (limit 200) |
| Range/bucket historical queries | `MIGRATED` (ad-hoc only — see item a) | `fmp/api/v1/tanks.py:112-114` `func.time_bucket`; frontend `web/src/pages/TankDetail.tsx:28` `rangeReadings` |
| Tank/site/company CRUD + alarms + strapping | `MIGRATED` | `fmp/api/v1/{tanks,companies,sites,stations}.py` |
| Totalizers series | `MIGRATED` | `fmp/api/v1/totalizers.py` |
| Login rate limiting (5/15min, locked out) | `MIGRATED` | `fmp/api/v1/auth.py:66-104`, `fmp/core/redis.py:rate_limit` |
| Token validation hardening (iss/aud/exp) | `IMPROVED` | `fmp/core/security.py` |
| Password reset (HMAC-token flow) | `DROPPED` | No reset/forgot endpoints (grep: 0 hits). Flagged for security audit (Task 4). |

### 3.6 Edge firmware (reference: User story + legacy worktrees)

| Capability (legacy) | Verdict | Current evidence |
|---|---|---|
| ESP32 firmware (firmware/mqtt_client, watchdog, buffer, keller RS-485) | `DROPPED` | No firmware in repo (verified by glob). Scheduled under Task 3: real ESP32 MicroPython firmware, sensor = **Modbus RTU pressure transmitter over RS-485** (register map not confirmed — will be configurable; assumptions documented). |

### 3.7 Health / deployment

| Capability (legacy) | Verdict | Current evidence |
|---|---|---|
| Containerized stack | `MIGRATED` | `docker-compose.yml` (redis, beat, db, db-init, api, emqx, ingest, nginx, web, worker) — verified up & healthy 2026-09-11 |
| `GET /health` | `MIGRATED` | `fmp/api/main.py`, `fmp/ingestion/main.py:349` |
| CI | `IMPROVED` | `.github/workflows/ci.yml` (pytest + pip-audit + tsc + vitest + npm audit) — pending commit |

## 4. High-priority parity gaps (a)–(e) — REQUIRED, pending decision

Each requires an integration test in `fmp/tests/integration/` against the live
docker-compose stack (not mocks), then either implementation **or** explicit user
sign-off that it is out of scope.

| # | Gap | Requirement |
|---|---|---|
| (a) | Continuous aggregates with **refresh policy** | `measurements_hourly` + `measurements_daily` materialized views via `add_continuous_aggregate_policy`; wire `GET /api/v1/tanks/{id}/range` (large windows) to them; refresh policy is the root-cause fix of the legacy bug. |
| (b) | Compression policy | `add_compression_policy('measurements', INTERVAL '7 days')` + enable on the aggregates (legacy *left this unconfigured* — this audits as `IMPROVED` once added). |
| (c) | Retention policy | `add_retention_policy('measurements', INTERVAL '30 days')` + deterministic test; optional nightly `drop_chunks`-based Celery task parity with legacy `cleanup_old_measurements`. |
| (d) | Consumption/forecast analytics | Daily consumption aggregation + a **forecast method to be confirmed with the operator** (do not invent a model). Add Celery task + API endpoint mirroring legacy `tasks/analytics.py`. |
| (e) | CSV export | `GET /api/v1/{tanks|measurements}/export` (date-range) streamed in batches (legacy used 1000-row batches), via Celery for large ranges. |

## 5. Explicit sign-offs collected (if any)

| # | Decision | Date | Signer |
|---|---|---|---|
| — | *(pending user review)* | | |

## 6. Open questions for the operator

1. (d) Forecast method: legacy report 01 did not specify the algorithm. Confirm
   one of: simple moving average, Holt-Winters, linear regression — or supply a
   spec. Nothing will be implemented until chosen.
2. All of (a)–(e): implement all, or sign off specific items as out of scope?
3. FlowRateCalculator (legacy) and password reset (legacy): both are `DROPPED`;
   not covered by (a)–(e). Keep dropped (recommended: password reset is a
   security-audit finding for Task 4), or add separately?

## 7. Auditor notes

- This audit intentionally does **not** re-add capabilities that legacy itself
  flagged as broken (missing refresh policy, unconfigured compression). Those
  become `IMPROVED` items (a)/(b) with the root cause fixed.
- All numerical deltas (row counts, test results) are captured in the Task 5
  final verification report, not here.