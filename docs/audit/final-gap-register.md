# Final Gap Register

**Date:** 2026-10-09
**Scope:** `/home/ubuntu/fuel_monitoring` at commit `8cc8bda`.

Status legend: **CLOSED** = implemented and verified against the running stack ·
**PARTIAL** = some of it done, remainder stated · **OPEN** = not done.

This register supersedes `gap-register.md`, which predates the hardening work.
Where the two disagree, this document is correct.

---

## Closed during this cycle

| ID | Gap | Evidence |
|---|---|---|
| G-001 | Broker accepted anonymous/unauthorised clients | EMQX password auth + deny-by-default + per-device ACLs; `scripts/provision_mqtt_accounts.py`; anonymous CONNECT and cross-device publish both refused |
| G-002 / G-113 | Dispensing and HTTP ingestion unauthenticated | Station key and `X-Ingest-Key` enforced; anonymous probes return 401/404 |
| G-003 | Cross-tenant leakage | Tenant scoping across organisations, assets, dispensing, analytics, totalizers, strapping, users, notifications, WebSockets, reports; `test_tenant_isolation.py` |
| G-004 | Alarms never cleared | Auto-resolve with hysteresis + Redis dedupe |
| G-005 | Notification credentials readable | Write-only/masked, tenant-scoped |
| G-102 | Custom-strapping tanks silently dropped readings | Strapping table now required and loaded; missing table logs an error instead of measuring wrongly |
| G-105 | Shared gateways visible across tenants | `iot_gateways.company_id` via migration `0004`; `tank_ids` filtered |
| G-201 | Liveness depended on the database | `/api/v1/health` is dependency-free; `/api/v1/readyz` carries dependencies |
| G-205 | Naive timestamps into a `timestamptz` column | Captured-at is always tz-aware |
| G-117 | Arabic/RTL claimed but not implemented | Catalogue + provider + RTL CSS + 21 tests. **PARTIAL — see OPEN-01** |
| — | Leaked EMQX credential committed to git | Rotated (old credential now returns 401), removed from all history with `git filter-repo`, provisioned file moved to a tracked directory |
| — | Ingestion dropped telemetry under burst | Was a real data-loss defect: one DB connection per frame exhausted the pool and **every subsequent frame failed**. Now queued and drained in batches |
| — | Per-frame commit amplification | 500-frame batch took 100s; now one commit per batch with a savepoint per frame |
| — | Unbounded memory growth | `IngestionPipeline._pending` grew forever and was never read |
| — | Health checks reported healthy services as unhealthy | EMQX `ctl` RPC, worker `celery inspect`, and the Python probes all had budgets smaller than their own startup cost |
| — | Frame loss invisible | Redis-backed counters on `/api/v1/metrics` and `/api/v1/metrics/prometheus`, with alert rules |
| — | Plaintext MQTT credentials | TLS listener on 8883 with `verify_peer` + `fail_if_no_peer_cert`; verified certless MQTT CONNECT is refused |
| — | Production could start insecurely | `model_validator` refuses `ENVIRONMENT=prod` without TLS, without a real `SECRET_KEY`, with an empty DB password, or with `DEBUG` |
| — | Tests shared a Redis with the live stack | `tests/conftest.py` pins `REDIS_DB=15`; two tests that failed against a live deployment now pass |
| — | Monolithic frontend bundle | Critical path 1.54 MB + 1.33 MB vendor → 173 kB + 287 kB; ECharts and three.js are lazy |
| — | Build context shipped dev caches | `platform/.dockerignore`; an image extract had failed with `no space left on device` |
| — | Deprecation warnings | `pubsub.aclose()`; test suite moved off the deprecated sync `TestClient` |

---

## Open

### OPEN-01 — Localization is 7 of 21 pages
**Severity: high.** `Dashboard`, `Tanks` (+ create dialog), `AlarmCenter`,
`ReportsPage`, `Login` and `Sidebar` use the catalogue. Still hardcoded English:
`UsersPage`, `AuditPage`, `IoTGatewaysPage`, `IoTGatewayDetailPage`, `SitesPage`,
`StationsPage`, `DispensersPage`, `Dispensing`, `FuelTypesPage`,
`NotificationRulesPage`, `NotificationLogPage`, `SettingsPage`, `TankDetail`,
`Totalizers`, and shared components (`TankTile`, `KpiCards`,
`AlertSummaryStrip`, `TankEditor`, `StrappingCard`, `ConsumptionCard`).

Consequence: the Arabic UI exists but is a shell. Any claim of a bilingual
product is premature until this closes.

### OPEN-02 — No browser-level verification
**Severity: high.** Every frontend result in this repo comes from Vitest, `tsc`
and the build. No test drives a real browser, so render errors, focus/ARIA
problems, broken responsive layouts and the RTL visual pass are all unverified.
Login → tank → alarm → report has never been exercised as a journey.

### OPEN-03 — Ingestion drain rate
**Severity: high.** Round trips per frame fell from ≥2 to 0.08 (8 SQL statements
per 100 frames, measured with a statement counter) and delivery is lossless. But
sustained throughput is unproven: on the measurement host a bare `SELECT 1` costs
~57 ms because the box runs at load 20–26 on 4 cores, giving ~3 fps regardless of
the code. Needs a dedicated host to establish a real ceiling.

### OPEN-04 — No capacity sign-off
**Severity: high.** Every latency figure in
`docs/operations/performance-capacity-report.md` is an upper bound from a
contended host. Resource envelope (sustained CPU, memory, container restarts) was
never characterised. The export optimisation is implemented and tested but its
speedup is unquantified.

### OPEN-05 — No alert delivery
**Severity: medium.** Prometheus rules exist and `frames_unaccounted` is
scrapeable, but Alertmanager ships a null receiver. Nothing actually pages.

### OPEN-06 — Secret rotation procedure
**Severity: medium.** TLS material is generated and git-ignored with `chmod 600`,
but there is no automated rotation, no expiry monitoring, and no documented
runbook for rotating the broker API key without dropping every device.

### OPEN-07 — Single-host topology
**Severity: medium.** api/ingest/worker/beat/db/redis/emqx all run on one host
with no redundancy, no backup schedule and no tested restore. A host failure is a
total outage.

---

## Environment, not product gaps

These distort measurements and were deliberately not "fixed", because the data
is not the repository's to delete:

- Host is shared with other projects; load ranged 4–26 per 4 cores.
- Disk was at 99% for most of the exercise (88% now), inflating all I/O.
- Two tests fail if the suite runs against a live stack sharing a Redis — fixed
  by REDIS_DB=15, but worth remembering as a class of problem.

---

## Known-quality issues

- `TankCanvas3D` chunk is 667 kB, `charts` (ECharts) 1.04 kB. Both are lazy and
  only fetched by tank detail, so the `chunkSizeWarningLimit` is raised to 1100 kB
  deliberately and documented.
- Frontend has no error boundary around chart rendering; a malformed analytics
  payload would surface as a blank card rather than a message.