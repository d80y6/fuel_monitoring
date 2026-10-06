# Phase 1 — Full System Audit

**Date:** 2026-09-15 · **Commit:** main@77d4234 · **Auditor role:** read before write; every claim verified against source and live runtime.

Severity scale: **P0** = blocks production / exploitable / data-loss or compliance breach · **P1** = material functional/security gap · **P2** = quality/ops gap · **P3** = hygiene.

Legend for feature status: ✅ fully implemented+verified · 🟡 partially implemented · 🔻 UI-only/backend-only · ❌ missing/broken · 🧪 mock/simulated.

---

## A. What this system ACTUALLY is (verified summary)

A single-tenant-in-practice fuel monitoring + dispensing-authorization platform:

- Edge: ESP32 MicroPython firmware → MQTT (EMQX) → standalone ingestion FastAPI (:8001) → TimescaleDB hypertables, Redis pub/sub.
- API (:8000 FastAPI): JWT auth w/ rotation+revocation, companies→sites→stations→dispensers CRUD, tanks + telemetry queries + CSV export, alarms (per-tank list+ack), dispensing workflow (Excel quota ingest → hashed authorization codes → validated dispense → totalizer audit), IoT gateway command channel w/ durable Redis queue + acks, consumption analytics + SMA forecast (Celery daily), notification gateways (real SMPP + WhatsApp Cloud API senders).
- Web (React 18/Vite, served via nginx): login, dashboard w/ live tiles + KPIs, tanks CRUD+create, tank detail (live 3D/2D canvas, GOV/NSV/density readouts, windowed charts, CSV export, strapping editor, consumption card), alarm center, dispensing (live view, allocations, code ops, upload), totalizer drift, companies/sites/stations/dispensers CRUD, fuel-types, notification-gateway config, IoT gateway mgmt + commands, settings (password change).
- Tests: platform pytest 150 unit + 50 integration (green vs fresh DB); web 202 vitest (green); tsc clean; build green.

## B. Domains audited (exhaustive inventory + verdicts)

### B.1 Frontend (pages × 16, routes under `/`)

| Route | Page | API wiring | Mutations | States (L/E/E/err) | Verdict |
|---|---|---|---|---|---|
| /login | Login | POST auth/login | real | ✓ | ✅ |
| /dashboard | Dashboard | tanks, fuel-types, stations, transactions, WS | n/a | ✓ | ✅ (KPIs derivations client-side, capped lists — D2) |
| /tanks | Tanks | tanks, fuel-types, sites | create | ✓(no err card) | 🟡 no edit/delete UI (API missing too) |
| /tanks/:id | TankDetail | tank, fuels, alarms, range, recent, export, consumption | ack | ✓ | 🟡 no stale-data indication (F3); strong page |
| /dispensing | Dispensing | stations, dispensers, transactions (poll), allocations (poll) | — | ✓ | ✅ (polling-based, not WS) |
| /dispensing tabs | Allocations/CodeOps/Upload | allocations/validate/complete/upload | real | ✓ | ✅ |
| /totalizers | Totalizers | totalizers, transactions | — | ✓ | ✅ |
| /alarms | AlarmCenter | per-tank alarms fan-out client-side (N+1), ack | ack | ✓ | 🟡 no global endpoint; level case bug (F2) |
| /companies | CompaniesPage | companies CRUD | full | ✓ | ✅ |
| /sites | SitesPage | sites CRUD (uses ?company= param) | full | ✓ | 🟡 NOT in sidebar nav (orphaned route) |
| /stations/:siteId | StationsPage | stations CRUD | full | ✓ | 🟡 only via drill-down |
| /dispensers/:stationId | DispensersPage | dispensers create/update | partial | ✓ | 🟡 only via drill-down |
| /admin/fuel-types | FuelTypesPage | list/create | create only | ✓ | 🟡 no edit/delete (API missing) |
| /admin/gateways | GatewaysPage | notification-gateways CRUD | full | ✓ | ✅ (shows provider secrets — F5 backend) |
| /admin/iot-gateways | IoTGatewaysPage(+Detail) | iot-gateways CRUD, commands, command history | full | ✓ | ✅ |
| /settings | SettingsPage | change-password | real | ✓ | 🟡 only password change exists |

### B.2 Backend/API
- Routers: 13 mounted + realtime WS. Endpoint matrix verified in code review. All REST endpoints use Pydantic schemas EXCEPT: ingest HTTP fallback (`frame: dict` F6) and dispensing/complete path OK (schema-validated).
- **Cross-cutting: NO tenant scoping anywhere** (P0-1); all list/get endpoints are global.
- **Missing API surfaces:** user management CRUD, org/tenant management, alarm rules config, global alarm list, reports, audit log, in-app notifications, regions, tank update/delete, fuel-type update/delete, dispenser delete, gateway-device credentials provisioning, site map endpoints, dashboard server-side aggregation.

### B.3 Database
- TimescaleDB hypertables (measurements, station_totalizers) + retention/compression/continuous aggregates ✅ (ingest task bootstraps them).
- Relational schema is coherent BUT: deployment uses `create_all` (init_db.py) — Alembic revision `0001_fuel_dynamics.py` exists but is **never applied in deploy** (P1). No FK cascade policy review needed (soft-delete model in place for org graph; tanks/alarms hard-delete cascade).
- No audit_log table. No per-user ↔ company link. No tag/group/region tables. Employee exists (dispensing only).

### B.4 AuthN/AuthZ
- JWT iss/aud locked down, refresh rotation+revocation (Redis + in-process fallback), PBKDF2 210k, password policy, login rate-limit (username+IP; Redis; fallback). ✅ solid core.
- Gaps: no user-admin API; role model only 3 flat roles and **role on JWT is not trusted blindly (DB re-loaded per request — good)**; WS token in query string (logged by proxies — P2); no MFA; ack endpoint trusts client-supplied `acknowledged_by` (P1); dispensing/validate+complete+upload unauthenticated (P0); provisioning of device credentials absent.

### B.5 Telemetry ingestion
- MQTT pipeline → validation-lite (float coercion) → geometry/density math (GOV/NSV/density, EMA, MAD outlier) → hypertable insert w/ ON CONFLICT DO NOTHING (idempotent to (tank_id,timestamp)) → Redis publish → WS fan-out. Real, quality engineering.
- **Defects**: anonymous broker auth (P0, live-verified injection); non-UUID command_id acks crash handler (P1/P2); custom_strapping tanks get NO strapping table passed → `ValueError` → **readings silently dropped** (P1); frames for unregistered tanks→negative-cache drop (by design, but no error surface/metric); `fuel/<mac>/readings` payload requires sensor_serial OR gateway resolution; HTTP fallback accepts arbitrary dict (P1); EMA/MAD state in-process only (lost on restart) (P3); naive `datetime.utcnow()` for captured_at fallback (P2).

### B.6 Alarms
- Threshold rules (5) evaluated in pipeline; dedupe via Redis open-set; persisted + published live. Frontend badge/ack flows.
- Gaps: alarm never **resolves** (open key never cleared → each alarm type fires once per Redis lifetime); no severity escalation, assignment, suppression, comments, maintenance windows, notifications; ack acknowledged_by spoofable; **stale-data→alarm: none**; sensor-fault (status≠0) ignored; water/pump alarms nonexistent (hardware model out of scope); frontend level case-sensitivity bug (P2); AlarmCenter N+1 queries.

### B.7 Notifications
- Real SMPP + WhatsApp Cloud API senders w/ retry + failover + NotificationLog persistence + test coverage integration. 
- Gaps: used ONLY for dispense codes — alarms never notify (P1); no email/webhook channel; English-only static message template (P2, product targets Arabic+English); provider creds exposed via GET to any authenticated user (P1); `dispatch_codes` awaited inline by HTTP upload handler blocking on external network+retries (P1); code plaintext temporarily in message (by design, single-use).

### B.8 Multi-tenancy → **ABSENT (P0)**
Verified: `list_companies`, `list_sites`, `list_tanks`, `list_stations`, dispensing lists, alarms, exports — all cross-tenant for any authenticated user; WS broadcasts all telemetry to every subscriber. Roles are global (admin / company_admin / user) with no company binding. Workflow 10 would fail across the board.

### B.9 Deployment/infra
- Compose valid; nginx security headers in place; CORS bounded by env; web image builds.
- Gaps: healthchecks only on db+redis (P2); api/ingest no readiness probe; EMQX anonymous (P0); MQTT 1883 exposed publicly by default; images not pinned by digest (P3); no backup/restore automation or docs; `.ruff_cache`/`.pytest_cache` checked into workspace but lint not wired to CI (P2/hygiene).

### B.10 Security (verified live)
- P0: anonymous MQTT publish accepted & persisted (demoed: inserted measurement row).
- P0: `/api/v1/dispensing/upload`, `/validate`, `/complete` unauthenticated (upload parses files and would mint codes + dispatch SMS).
- P1: notification gateway secrets readable by any authenticated user.
- P1: tenant isolation absent (all data cross-visible).
- P2: `/api/v1/realtime/metrics` unauthenticated; WS token in URL; login 429-throttle only AFTER N failures (enum-safe — good), but no captcha/lockout for distributed attempts.
- P2: `acknowledged_by` from query param.

### B.11 Observability/ops
- Structured-ish logs via stdlib logging; no correlation IDs, no metrics endpoints (except /api/v1/realtime/metrics unauth), no /ready; docker healthchecks partial; no alert-on-platform-failure path. P1/P2.

### B.12 Testing
- Broad suites exist & are green (unit 150, integration 50, web 202). Gaps: no tenant-isolation tests (because feature absent), no E2E browser tests, no security regression suite for the exploits above, one destructive "unit" test (`test_celery_loop_safety`) that mutates the configured DB, perf tests absent.

### B.13 Documentation
- Rich and largely current; contradictions: audit-filename reference stale; technical spec describes vision (multi-tenancy etc.) not current reality; MQTT protocol doc vs anonymous broker config; README claims "JWTs, RBAC" (true) but nothing on tenant isolation (absent).

### B.14 Performance/scalability
- Reasonable foundations (Timescale chunks/aggregates, batched inserts, Redis fast paths, streaming CSV). Unmeasured load; AlarmCenter N+1; KPI derivation client-side from truncated lists; no pagination on several lists; `list_allocations`/`transactions` capped but not paged. No soak/perf evidence → P2.

### B.15 i18n/RTL/a11y
- English only; **no i18n framework, no RTL** (P1 for Arabic-market claim); a11y is partial (labels/keyboard on dialogs, sr-only column) but no focus traps, no RTL, no color-independent status semantics everywhere, no locale date/number formatting strategy.

---

## C. Root-cause themes
1. Built initially as single-tenant ops console; tenant dimension never added to identity model.
2. Edge trust boundary never secured (broker anonymous; ingest unauthenticated).
3. Domain decomposition strong internally (models/services coherent) but lifecycle/admin surfaces (users, rules, reports, audit) never built.
4. Frontend↔backend contract drift (roles.ts, AlarmSummary.level case) — no contract tests across that seam except ad-hoc vitest mocks.
