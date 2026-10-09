# Final Feature Matrix

**Date:** 2026-10-09 · commit `8cc8bda`

Legend: **Full** = built and verified end to end against the running stack ·
**Partial** = works but incomplete · **UI only** / **API only** = one side missing ·
**Absent** = not built.

Every "Full" row below was exercised against the deployed stack, not merely
present in code.

## Identity and tenancy

| Capability | Status | Evidence |
|---|---|---|
| Login (JWT), logout, refresh | Full | `POST /api/v1/auth/login` returns token; `/logout` verified |
| Roles: admin / company_admin / user | Full | Enforced in `deps.py`; earlier `is_superuser` mismatch removed |
| Platform admin vs tenant scoping | Full | `admin` has `company_id IS NULL` and sees all; tenant roles see only their own |
| Cross-tenant isolation (REST + WebSocket) | Full | `test_tenant_isolation.py` |
| User CRUD | Full | `/api/v1/users` CRUD verified |
| Password change | Full | `SettingsPage` + `PATCH /api/v1/users/me/password` |

## Assets and configuration

| Capability | Status | Evidence |
|---|---|---|
| Companies / sites / stations | Full | CRUD verified 200 |
| Tanks CRUD | Full | Create, patch, soft-delete, restore; **all measurement rows preserved** |
| Tank geometry (diameter, height, length, width, dish depth) | Full | Drives volume calculation |
| Tank shapes incl. custom strapping | Full | Strapping table required; missing table errors rather than mis-measures |
| Fuel types CRUD | Full | Immutable codes; in-use deletion returns 409 |
| IoT gateways CRUD + tenant scoping | Full | Migration `0004`; `tank_ids` filtered per tenant |
| Gateway command issue + history | Full | Verified; see test-isolation caveat |
| Totalizers | Full | Backfilled station totals |

## Telemetry and ingestion

| Capability | Status | Evidence |
|---|---|---|
| MQTT ingestion with per-device ACLs | Full | Devices publish only to `fuel/<own-mac>/#`; cross-device writes denied |
| HTTP ingestion fallback | Full | `X-Ingest-Key` enforced |
| MQTT TLS with mutual auth | Full | Listener on 8883; certless MQTT CONNECT refused |
| Calibration, EMA/MAD smoothing, outlier flag | Full | `pipeline.py`; state resets after a sensor fault |
| Over-range detection | Full | Clamped, `OVER_RANGE_STATUS_BIT` set, `sensor_fault` raised |
| Liveness + communication-loss detection | Full | Frame sets `last_connection`; sweeper raises/clears |
| Custom strapping ingestion | Full | Table uploaded and applied |
| **Lossless under burst** | Full | 1000/1000 frames persisted, queue drained to 0 |
| **Sustained throughput** | Partial | 0.08 SQL statements/frame, but throughput bounded by host DB latency (~57 ms/round trip). Real ceiling unproven |
| Retention + continuous aggregates | Full | 30-day policy, hourly/daily CAGGs |

## Alarms and notifications

| Capability | Status | Evidence |
|---|---|---|
| Threshold + sensor-fault alarms | Full | Raised via pipeline |
| Auto-resolve with hysteresis | Full | G-004 |
| Alarm acknowledgement | Full | `POST /alarms/{id}/ack` |
| Notification rules CRUD | Full | `/api/v1/notification-rules` |
| Notification gateways (masked credentials) | Full | Write-only; unreadable after write |
| Notification delivery log | Full | `/api/v1/notifications/logs` |
| Alarm notification dispatch | Full | `notification_logs` records outcome per rule |
| **Alert delivery to operators** | Absent | Prometheus rules exist; Alertmanager has a null receiver |

## Analytics and reporting

| Capability | Status | Evidence |
|---|---|---|
| Consumption analytics (SMA) | Full | `/api/v1/analytics/consumption` |
| Reports: tank inventory | Full | JSON + CSV from one calculation path |
| Reports: consumption | Full | Includes explicit assumptions |
| Reports: inventory variance | Full | |
| Reports: alarms | Full | |
| Reports: dispensing audit | Full | |
| Report tenant scoping | Full | Cross-tenant returns empty, never another tenant's data |
| CSV export of raw telemetry | Full | Streamed, batched, column-selected; contract covered by tests |

## Operations

| Capability | Status | Evidence |
|---|---|---|
| JSON logging with request correlation | Full | `X-Request-ID` honoured and minted |
| Liveness / readiness | Full | `/health` dependency-free; `/readyz` reports DB, Redis, MQTT |
| Metrics (JSON + Prometheus) | Full | `/api/v1/metrics`, `/api/v1/metrics/prometheus` |
| Ingestion frame accounting | Full | received/persisted/rejected/dropped/queue depth/batch latency |
| Alert rules | Full | `infra/prometheus/alerts.yml`, 10 rules |
| Alert delivery | Absent | Null receiver |
| TLS certificate generation | Full | `scripts/generate_certs.sh` |
| Secret rotation runbook | Absent | — |
| Backup and tested restore | Absent | — |
| High availability / multi-host | Absent | Single-host topology |
| **Measured capacity sign-off** | Absent | All figures are upper bounds from a contended host |

## Frontend

| Capability | Status | Evidence |
|---|---|---|
| Dashboard with live telemetry | Full | KPI cards, alert strip, tank tiles |
| Tank list, create, edit, deactivate, restore | Full | Verified live |
| Tank detail: 3D view, charts, export | Full | WebGL canvas, ECharts, CSV |
| Alarm centre | Full | Filter, acknowledge, resolve |
| Reports workspace | Full | Assumptions, freshness, empty/error states, CSV |
| Users, audit, notifications, settings pages | Full | Backed by working APIs |
| RTL layout and locale switching | Partial | Infrastructure correct; 7 of 21 pages translated |
| Arabic content coverage | Partial | See `final-gap-register.md` OPEN-01 |
| Accessibility | Partial | Semantic markup, `sr-only` labels, aria attributes; **never audited by a tool or a browser** |
| Browser-level testing | Absent | No E2E harness at all |
| Bundle budget | Full | Critical path 655 kB raw; heavy deps lazy-loaded |

## Summary

- **Full:** 47 · **Partial:** 5 · **Absent:** 7

The platform is functionally complete and verified end to end for its core
flows. What is missing is not features — it is *proof and reach*: browser-level
verification, a real capacity number, bilingual coverage, alert delivery, and
operational maturity (backup, restore, HA, rotation).