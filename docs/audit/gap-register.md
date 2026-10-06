# Gap Register — main@77d4234 (2026-09-15)

Status legend: OPEN / FIXED / VERIFIED. Priorities P0>P1>P2>P3.

## P0 — blockers (security / correctness / tenancy)

| ID | Domain | Finding | Root cause | Required fix | Verification |
|----|--------|---------|-----------|--------------|--------------|
| G-001 | security/edge | EMQX anonymous: `authorization{no_match="allow"}`, no `authentication` block, no per-device creds; **verified: anonymous publish from host persisted a forged measurement row** | broker auth never enabled | Enable EMQX authentication (built-in DB w/ per-gateway users) + ACL rules; provision creds; stop publishing 1883 publicly in prod; docs | anonymous publish rejected; authorized client passes |
| G-002 | security/api | `/api/v1/dispensing/upload`, `/validate`, `/complete` unauthenticated (verified 200/400 without token) | device-facing endpoints mixed into public API with no auth dep | Add device-auth dependency (station API key infra) or internal network restriction; nginx gate `/api/v1/dispensing/*` to internal | 401 unauthenticated; e2e dispensing w/ device key |
| G-003 | multi-tenancy | No tenant dimension on User; all endpoints return all orgs' data; WS broadcasts all telemetry | feature never built | Tenant model: user.company_id, scopes for every query + WS filtering; admin cross-tenant | isolation test suite (2 tenants, all endpoints) |
| G-004 | alarms | Alarms never auto-resolve; Redis open-set never cleared → each alarm type fires once ever per tank | resolve path never written | Resolution eval in pipeline + `resolved_at`/`resolved_message` + auto-clear open key; keep history | simulate high→low crossing; alarm active→resolved |
| G-005 | security/api | `GET /notification-gateways` returns `config_json` (SMPP password / WhatsApp token) to ANY authenticated user | read schema leaks secret config | Secrets write-only in API (mask on read; separate update validation); test | GET redacts secrets for non-admin; admin gets masked + reference |

## P1 — material gaps

| ID | Domain | Finding | Root cause | Required fix | Verification |
|----|--------|---------|-----------|--------------|--------------|
| G-101 | frontend | `roles.ts: canManage('admin'|'manager')` vs backend `company_admin` → company_admin locked out of all `/companies`,`/sites`, admin routes, dispensing upload tab | drift, never caught (no cross-tier role contract test) | fix role fn + shared contract test via tests | company_admin reaches pages; vitest asserts mapping from backend enum |
| G-102 | telemetry | `tank_shape='custom_strapping'` tanks: pipeline omits `strapping=` → ValueError swallowed → **all their measurements silently dropped** | param not threaded | load strapping in pipeline; pass to geometry; unit+integration test | custom-strapping tank ingests + computes volume |
| G-103 | telemetry/alarms | No stale/communication-loss detection: `tanks.connection_status` stays "online" forever; nothing sweeps silence | no beat task | heartbeat/stale sweeper (Celery): mark offline after N sec, raise/clear `communication_lost` alarm, emit live event | stop frames → alarm + UI stale indicator; resume → clear |
| G-104 | api | No user-management API (no create/list/deactivate/role/company assignment); only seeded admin exists | never built | `/api/v1/users` CRUD (admin) w/ password policy + company assignment | integration tests; admin creates company_admin scoped to org |
| G-105 | api | Tanks: no PATCH/DELETE; FuelType: no PATCH/DELETE | never built | add update/deactivate (soft-delete tanks; guard fuel-type delete w/ usage check); FE wiring | CRUD e2e via UI |
| G-106 | api | Alarm ack takes `acknowledged_by` from query param (spoofable) | shortcut | use authenticated user id | 400/403 on spoof; integration test |
| G-107 | api/frontend | No global alarm list endpoint; AlarmCenter fans out N+1 per-tank queries | convenience shortcut | `GET /api/v1/alarms?status=&site=&company=` w/ pagination; refactor page | e2e: one request path; scale-safe |
| G-108 | reporting | No reporting subsystem (no inventory/delivery/variance/alarm reports; only per-tank CSV export) | never built | reports module: JSON+CSV for tank inventory, consumption, alarms, dispensing audit; date range + scope filters; permission-aware | report integration tests + UI export |
| G-109 | db/deploy | Deploys via `create_all`; Alembic chain (`0001_fuel_dynamics.py`) never applied; drift risk | bootstrap shortcut | alembic as deployment migration path (init via alembic upgrade; baseline existing DB via stamp) | fresh DB `alembic upgrade head`; stamp path verified in CI container |
| G-110 | security | Frontend `roles.ts` duplicates backend model; `requireManage` references nonexistent `is_superuser` | contract drift | single source: backend /me returns role enum; frontend types generated/aligned | contract test asserts roles from OpenAPI |
| G-111 | frontend | No Sites nav entry; Stations/Dispensers reachable only by deep link | shell IA gap | nav restructure (see IA section); breadcrumbs | nav reachable; e2e walk |
| G-112 | notifications | Alarms never notify (SMS/WhatsApp/email/webhook); only code dispatch wired | never built | notification rules: alarm event → recipients (role/site scoped) → channels; quiet hours optional | alarm→SMS/webhook mocked+integration test |
| G-113 | auth | No devices/station identities for M2M: validate/complete keyed on `station_id` UUID only, no secret | design gap | station API key (hashed) + `X-Station-Key` for dispensing + ingest; rotate | unauthorized station rejected |
| G-114 | ingest | HTTP fallback accepts arbitrary `dict` (no schema) | raw dict | Pydantic frame schema; reject malformed w/ 422 | invalid payload 422 test |
| G-115 | ingest | Ack handler crashes on non-UUID `command_id` (observed in live logs) | direct UUID column bind | tolerant parsing + dead-letter log | malformed ack handled, logged |
| G-116 | audit | No audit log (who acked/changed thresholds/created users/gateways) | never built | `audit_events` table + middleware/service hooks for mutating endpoints | configuring rule creates audit row |
| G-117 | i18n | No i18n/RTL; English-only | never built | i18next + ar/en resources + `dir` handling + locale-aware formatting | language toggle; RTL layout renders correctly |
| G-118 | test | `test_celery_loop_safety` hits live DB (deletes gateways) in whatever env POSTGRES points at | mis-scoped unit test | move under integration + guard on strong test-env marker | unit suite passes w/o DB; destructive paths only on fuel_test — **FIXED 2026-09-17**: module-scoped `_require_test_database()` guard refuses non-test DBs (`pytest.exit`) before any fixture connects; verified pass on `fuel_test` and hard refusal on `fuel_monitoring` |
| G-119 | deps/CI | npm audit: 8 vulns incl. 1 critical/1 high; pip-audit missing locally | no dependency policy | bump echarts/react-router/vite chains; add pip-audit to dev reqs + CI (CI has it; keep green) | audits clean or justified exceptions |
| G-120 | ingest | EMA/MAD per-tank state in-process → restart resets smoothing window | in-process stateless | document/accept (EMA warm-up quick) — downgrade to P3 accepted limitation |

## P2 — ops / perf / consistency

| ID | Domain | Finding | Fix |
|----|--------|---------|-----|
| G-201 | obs | No request-id/correlation; logs unstructured; no /ready probes; compose healthchecks only db+redis | request-id middleware, JSON logs, /readyz per service, compose healthchecks |
| G-202 | ws | WS token in query string (logged by middleware); channel filter not per-tank scoped | Sec-WebSocket-Protocol auth or short-lived ticket; optional per-tank channels honoring ACL |
| G-203 | api | No pagination on list endpoints (tanks/sites/companies/allocations/transactions hard caps) | add limit/offset + total headers on hot lists |
| G-204 | frontend | KPI 24h dispensed derives from capped transaction window | server-side dashboard aggregate endpoint |
| G-205 | consistency | `datetime.utcnow()` naive writes into tz-aware cols (ack, soft_delete, captured fallback) | tz-aware now everywhere; lint hook |
| G-206 | security | images unpinned digests; emqx 18083 dashboard default creds doc'd weakly | pin image digests; document EMQX admin bootstrap rotation |
| G-207 | frontend | Bundle 1.4MB/461KB gz single chunk; three.js lazy but echarts in main chunk | manualChunks code-split |
| G-208 | frontend | Settings only password change | add profile display + notification prefs placeholder→real when rules land |
| G-209 | security | login 429 only after failures measured per (username,IP); no distributed defense | document as accepted; optional IP-only second bucket (implemented) |
| G-210 | api | `DispenseComplete` OVER_DISPENSE semantics: txn logged status=OVER_DISPENSE but 500-style? check summary | verify UI surface; document |

## P3 — hygiene
| ID | Finding | Fix |
|----|---------|-----|
| G-301 | stale `.pyc`-only dirs (`services/`,`tasks/`,`templates/`,`utils/`,`data/` junk), `.worktrees/` merged branches | delete (git rm), cleanup |
| G-302 | README doc-index filename mismatch (`2026-XX-security-audit.md`) | fix link |
| G-303 | two package-lock files (npm + pnpm lock) | standardize npm (CI uses npm ci) |
| G-304 | `web/dist` committed? (verify .gitignore) | ignore |
| G-305 | legacy alembic env naming/mismatch with app Base | align |

## Accepted limitations (documented; not gaps)
- Water-level / pressure-only hardware model: current probe is bottom pressure + temperature; water bottom-cut gauge would need a second probe → firmware & processor extension deferred (protocol-ready).
- EMA/MAD smoothing warm-up after ingest restart (transient, seconds-worth of frames).
