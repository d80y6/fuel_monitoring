# Commercial Hardening Implementation Plan

**Goal:** Close all P0 + P1 gaps from docs/audit/gap-register.md and move the platform to deployable multi-tenant commercial readiness; keep every existing green test green.

**Architecture decisions (documented):**
- D1 Tenant = existing `companies` entity. Add `users.company_id`; scopes resolved per-request via `tenant_scope(user)` helper. `admin` = platform operator (cross-tenant), `company_admin`/`user` = tenant-bound.
- D2 Device auth: station API keys (`stations.api_key_hash` PBKDF2) for dispensing paths; shared ingest key for HTTP fallback; EMQX built-in-DB authn + ACL (username=gateway MAC, only `fuel/<mac>/+` topics).
- D3 Alarm lifecycle: add state fields; pipeline resolves on recovery; new beat task `telemetry.sweep_stale` flips `connection_status` to offline + raises comm-loss alarm; heartbeat clears.
- D4 Reports = server-generated CSV/JSON scoped queries.
- D5 Audit events table + hooks on mutating endpoints.
- D6 Alembic becomes the schema path: baseline revision == current models; follow-on migration for all new schema; `init_db` runs `alembic upgrade head` (stamps legacy DBs first).
- D7 i18n via react-i18next (en/ar) + `<html dir>` switching.

**Verification gates after each task:** backend pytest, integration pytest, tsc, vitest, build; live compose checks for security fixes.

## Tasks

1. **Schema foundation + alembic** — baseline migration, upgrade deploy path, fix tests baseline. Files: platform/alembic/*, fmp/scripts/init_db.py.
2. **Tenancy core** — user.company_id, tenant_scope helper, UserRead/Create schemas, `/api/v1/users` CRUD, seed updates, isolation tests.
3. **Scope enforcement pass** — all routers + WS filtering by company; dispensing identity.
4. **Device auth** — station api keys, ingest key dep, EMQX authn/acl, gateway cred provisioning script, tests.
5. **Alarm lifecycle + comm-loss** — resolved state, pipeline resolution, sweep task, notifications on alarm (email/webhook/smrt dispatch rules), normalization of level values.
6. **Reports** — inventory/consumption/alarm/dispensing reports JSON+CSV scoped.
7. **Audit log** — model + hooks + read API.
8. **CRUD completion** — tank PATCH/DELETE, fuel-type PATCH, dispenser DELETE.
9. **Ops** — /readyz deep checks, request-id middleware, compose healthchecks, requirements-dev w/ pip-audit, ruff config+CI lint.
10. **Frontend pass 1 (contract fixes)** — roles.ts, alarm level case, Sites nav, freshness indicators, settings.
11. **Frontend pass 2 (new domains)** — Users admin, Reports, Audit pages, org selector for admin, tank edit/delete UI, fuel-type edit.
12. **i18n + a11y** — i18next, en/ar catalogs, RTL switch, aria/focus gaps on modals/tables.
13. **Hygiene** — remove legacy dirs, fix locks/dedup, README/docs refresh, doc index fixes.
14. **Final validation** — full suites, compose rebuild, live exploit retests, e2e workflow scripts.

Every phase must leave the tree in a green state.
