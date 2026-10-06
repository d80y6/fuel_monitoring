# Phase 0 — Baseline Report

**Date:** 2026-09-15
**Repository:** git@github.com:d80y6/fuel_monitoring.git (local: `/home/ubuntu/fuel_monitoring`)
**Branch / commit:** `main` @ `77d4234e4dbe8cc86bd9d78337424de81454d4d9` ("Merge branch 'wire-backend-gaps' into main")
**Working tree:** clean. All local branches (`feat/frontend-completion`, `fuel-dynamics-scada`, `scada-frontend`, `status`) are fully merged into `main`. Two stale worktrees exist under `.worktrees/` pointing at merged heads.

## 1. Stack inventory

| Layer | Technology / version (observed) |
|---|---|
| Backend API | FastAPI (requirements pin `fastapi>=0.115,<1.0`), Python 3.12, uvicorn, async SQLAlchemy 2.0 + asyncpg |
| Database | TimescaleDB `timescale/timescaledb:2.11.0-pg14` (PostgreSQL 14 + Timescale 2.11). Host psql client 16.15 (not used by app) |
| Cache/broker | Redis 7-alpine (appendonly), Celery 5.3 worker + beat |
| MQTT | EMQX 5.8 community (`infra/emqx/emqx.conf`) |
| Ingestion | Standalone FastAPI service `fmp.ingestion.main` (:8001) + paho-mqtt 2.x |
| Frontend | React 18.3, Vite 5.4, TypeScript 5.6, Tailwind 3.4, TanStack Query 5, Zustand 4, React Router 6.26, ECharts 5.5, three.js |
| Edge firmware | MicroPython under `firmware/` (ESP32, MQTT+TLS, RS-485) |
| Deploy | Docker Compose (`name: fuel-platform`, 10 services), nginx 1.27 reverse proxy on :80 |
| CI | `.github/workflows/ci.yml`: backend pytest (Timescale+Redis services) + pip-audit; frontend tsc + vitest + npm audit |

## 2. Environment

- Python 3.12.3 (system; backend deps importable), Node 22.22.3 / npm 10.9.8
- Docker 29.7.2, Compose v5.1.3
- Full stack already running: `fuel-platform-{db,redis,emqx,api,ingest,worker,beat,nginx,web}` up ~1h; db+redis healthy; DB/Redis ports NOT published to host.
- `.env` present (values not disclosed here); `ENVIRONMENT`/`DEBUG`/`SECRET_KEY`/`POSTGRES_HOST`/`MQTT_BROKER` all set.

## 3. Baseline commands and results

| # | Command | Result | Notes |
|---|---------|--------|-------|
| 1 | `docker exec fuel-platform-api-1 pytest -q --ignore=fmp/tests/integration` | **150 passed, 1 FAILED** | Failure: `tests/unit/test_celery_loop_safety.py::test_sweep_commands_survives_repeated_asyncio_run` — `IntegrityError: DELETE FROM iot_gateways` violates FK `tanks_gateway_id_fkey`. See F-0-1. |
| 2 | `docker exec -e POSTGRES_DB=fuel_test fuel-platform-api-1 pytest -q fmp/tests/integration` | **50 passed** (1m56s) | Full integration suite green against `fuel_test` schema. |
| 3 | `web: npx tsc --noEmit` | **PASS** (exit 0) | |
| 4 | `web: npx vitest run` | **47 files / 202 tests passed** | React Router v7 future-flag warning printed. |
| 5 | `web: npm run build` | **PASS** | `vite build` OK. Warnings: chunks >500 kB (`index` 1.43 MB / 461 kB gzip, `TankCanvas3D` 824 kB / 223 kB gzip). |
| 6 | `web: npm audit --audit-level=high` | **8 vulns (6 moderate, 1 high, 1 critical)** | echarts <6.1.0 XSS (GHSA-fgmj-fm8m-jvvx); esbuild ≤0.24.2 dev-server (GHSA-67mh-4wv8-2f99); react-router 6.0–7.17 (GHSA-wrjc-x8rr-h8h6, GHSA-337j-9hxr-rhxg); vitest/vite/vitest-mocker path traversal (GHSA-82fw-gwwq-j7x9). See F-0-2. |
| 7 | `pip-audit` (backend) | **N/A** | Not installed in image; only run in CI. GAP — cannot validate locally (F-0-3). |
| 8 | `curl http://localhost:80/api/v1/health` (nginx) | **200** `{"status":"ok","service":"api"}` | |
| 9 | `curl http://localhost:80/` | **200** SPA shell | Served index references older bundle hash than current build — running web image is stale relative to working tree (rebuild required to reflect source). |
| 10 | Docker build | **Previously built** | Images exist and stack runs from them; full clean rebuild not re-executed in Phase 0 (deferred to deployment validation phase). |
| 11 | Alembic migrations | **NOT WIRED** | `platform/alembic/` exists with single revision `0001_fuel_dynamics.py`, but runtime bootstrap is `fmp/scripts/init_db.py` using `Base.metadata.create_all`. Migration chain not exercised by deploy. (F-0-4) |
| 12 | Linting (ruff/flake8/mypy) | **NOT CONFIGURED** | No `pyproject.toml`, ruff/flake8 config, or lint step in CI; stray `.ruff_cache/` artifacts only. (F-0-5) |

## 4. Baseline findings (pre-audit)

| ID | Severity | Component | Finding |
|----|----------|-----------|---------|
| F-0-1 | P1 | tests | `tests/unit/test_celery_loop_safety.py` is placed under `unit/` but requires live Postgres and **destructively deletes `iot_gateways` / `notification_gateways` / logs** in whatever DB env points at. Fails against a non-empty dev DB; passes in CI only because CI DB is empty. Non-hermetic, risk of dev/prod data loss if run with wrong env. |
| F-0-2 | P1 | deps | 8 npm vulnerabilities incl. 1 critical/1 high; backend pip-audit not runnable locally. |
| F-0-3 | P2 | tooling | pip-audit only in CI; no local backend dependency scanning path in requirements-dev. |
| F-0-4 | P1 | database | Deploy path uses `create_all`, not Alembic. `alembic/versions/0001_fuel_dynamics.py` exists but `alembic upgrade` is never run by Compose/CI/docs. Schema drift between models and existing DBs is unmanaged. Rollback strategy absent. |
| F-0-5 | P2 | tooling | No backend lint config/CI step. |
| F-0-6 | P1 | security (observed, full audit to confirm) | `infra/emqx/emqx.conf`: no `authentication` block; `authorization no_match="allow"` with empty built-in DB ⇒ anonymous publish/subscribe to all topics accepted from network. Port 1883 published to host. |
| F-0-7 | P1 | security (observed) | Ingest HTTP endpoints `/api/v1/ingest/readings` + `/api/v1/ingest/backfill` are unauthenticated at the FastAPI layer, and nginx proxies `/ingest/` publicly. Telemetry injection path appears open. |
| F-0-8 | P2 | ops | Compose defines healthchecks only for db+redis; api/ingest/worker/beat/web have none. Ingest health exists at `/api/v1/health` (not `/health`). |
| F-0-9 | P3 | repo hygiene | Stale `.pyc`-only content under `services/`, `tasks/`, `templates/`, `utils/` (legacy Flask-era directories, bytecode only). Stale merged worktrees under `.worktrees/`. |
| F-0-10 | P3 | docs | `README.md` "Documentation index" references `docs/security/2026-XX-security-audit.md` — actual file is `2026-09-11-security-audit.md`. |

## 5. Existing functional surface (initial inventory, to be verified in Phase 1)

- **Backend routers:** auth, companies, sites, stations, tanks, fuel_types, strapping, dispensing, iot_gateways, notifications, analytics, realtime, totalizers (+ platform `api/realtime.py`).
- **Models:** user, station, tank, fuel, dispensing, gateway, notifications, analytics, base.
- **Ingestion:** MQTT pipeline, batch writer, cache (tank resolution + negative cache), relay (gateway commands), tank_geometry, tsdb_policies.
- **Services:** auth, dispensing (code_generator, dispense_engine, excel_ingestion), notifications/dispatcher, analytics/consumption.
- **Workers:** celery_app + tasks (analytics, notifications, commands).
- **Frontend pages:** Login, Dashboard, Tanks, TankDetail, Stations, Sites, Companies, FuelTypes, IoTGateways, IoTGatewayDetail, Gateways, Dispensers, Dispensing, Totalizers, AlarmCenter, Settings.
- **Tests:** backend ~22 unit + ~22 integration files; frontend 47 vitest files (green).

## 6. Discrepancies from expected baseline

1. `fuel_test` database already existed in the running Postgres (left over from earlier CI-like runs).
2. Served SPA bundle is out of date relative to `web/src` (image not rebuilt after latest source changes).
3. `rtk` wrapper tooling present in environment (compressed `ls`/`read` outputs — not part of repo).

— End of baseline. Proceed to Phase 1 (complete system audit).
