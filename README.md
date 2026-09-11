# Cloud Fuel & Dispensing Platform

Cloud platform for fuel tank monitoring (pressure/temperature/level telemetry via MQTT) and
fuel dispensing authorization (OTP code generation, allocation quotas, dispenser validation).

**Current architecture:** FastAPI (Python 3.12, async SQLAlchemy) + React 18 (Vite + TypeScript).
The console stack runs on Docker Compose with TimescaleDB, Redis, EMQX (MQTT broker), Celery worker/beat,
and nginx. Edge devices (ESP32 firmware) publish tank sensor readings over MQTT; a dispenser controller
(Raspberry Pi / Modbus) interacts with the dispensing API.

> **Historical note:** the previous Flask-era codebase was deleted. Its documentation is archived under
> [`docs/archive/legacy-flask/`](docs/archive/legacy-flask/). It does **not** describe the current system.

---

## Table of contents

- [Architecture](#architecture)
- [Repository layout](#repository-layout)
- [Prerequisites](#prerequisites)
- [Quick start (Docker Compose)](#quick-start-docker-compose)
- [Generating `.env` from `.env.example`](#generating-env-from-envexample)
- [Manual steps before first boot](#manual-steps-before-first-boot)
- [Local development without Docker](#local-development-without-docker)
- [Running tests](#running-tests)
- [MQTT protocol](#mqtt-protocol)
- [Documentation index](#documentation-index)

---

## Architecture

```
Edge layer              Message broker          Ingestion layer          Data layer / API                              Presentation
┌─────────────┐   MQTT  ┌──────────┐   subscribe ┌─────────────────┐   ┌──────────────────┐   REST / SSE / WS   ┌─────────────┐
│ ESP32 gateway ├──────▶│  EMQX    ├────────────▶│ Edge Ingestion   ├──▶│ FastAPI +         ├───────────────────▶│ React SPA    │
│ (RS-485 sensor)│      │ (:1883/  │             │ FastAPI (:8001)  │   │ SQLAlchemy /      │  nginx reverse    │ (Vite)      │
└─────────────┘         │  :8883)  │             └─────────────────┘   │ TimescaleDB +     │  proxy :80        └─────────────┘
┌─────────────┐         └──────────┘                                   │ Redis + Celery    │
│ Dispenser   │                │ API publishes                          └──────────────────┘
│ controller  │◀─────── command topics (dispense/+/code_response)
└─────────────┘
```

- **`api`** — central FastAPI application on `:8000` (`fmp.api.main`). REST under `api/v1/`, JWTs, RBAC, WebSockets.
- **`ingest`** — edge ingestion FastAPI application on `:8001` (`fmp.ingestion.main`). Subscribes to MQTT topics,
  validates payloads, bulk-writes measurements to TimescaleDB, publishes update events via Redis.
- **`worker` / `beat`** — Celery for notifications (SMS/WhatsApp), reports and Excel ingestion.
- **`web`** — React SPA built into an nginx container (`:8080` internal), served behind the main nginx proxy.
- **`firmware/`** — MicroPython firmware for the ESP32 edge gateway (MQTT + TLS, offline buffering, RS-485 sensor read).

See [`docs/architecture/SYSTEM_ARCHITECTURE.md`](docs/architecture/SYSTEM_ARCHITECTURE.md) and
[`docs/TECHNICAL_SPECIFICATION.md`](docs/TECHNICAL_SPECIFICATION.md) for detailed diagrams.

## Repository layout

```
.
├── docker-compose.yml      # full stack orchestration
├── .env.example            # environment template (copy → .env)
├── infra/                  # nginx + EMQX configuration
├── platform/               # Python backend (FastAPI, fmp package, Alembic)
│   └── fmp/
│       ├── api/            # FastAPI app + routers under api/v1/
│       ├── core/           # config, database, redis, security (JWT/PBKDF2)
│       ├── ingestion/      # MQTT edge ingestion engine
│       ├── models/         # SQLAlchemy models
│       ├── schemas/        # Pydantic schemas
│       ├── services/       # auth, dispensing, notifications
│       ├── workers/        # Celery app + tasks
│       └── tests/          # unit + integration tests (pytest)
├── web/                    # React 18 + Vite + TypeScript frontend
└── docs/                   # architecture docs, security audit, MQTT protocol, archive
```

## Prerequisites

- Docker Engine 24+ with Docker Compose v2 (`docker compose`).
- For local (non-Docker) development: Python 3.12, Node.js 18+ / npm 9+.

## Quick start (Docker Compose)

```bash
cp .env.example .env        # then edit required secrets (see below)
docker compose up --build
```

This starts: TimescaleDB, Redis, EMQX, `db-init` (idempotent schema + seed), `api` (:8000),
`ingest` (:8001), Celery `worker` + `beat`, nginx reverse proxy (:80) and the `web` SPA.

- API health check: `curl http://localhost:80/api/v1/health`
- Swagger UI: `http://localhost:80/api/docs`
- EMQX dashboard: `http://localhost:18083`

Useful commands:

```bash
docker compose logs -f api          # follow API logs
docker compose restart ingest        # restart the MQTT ingestion engine
docker compose down                  # stop the stack (keeps named volumes)
docker compose down -v               # stop + delete volumes (destructive — backups first)
```

## Generating `.env` from `.env.example`

`.env` is **not** committed and is ignored by git. Generate it and fill in real values:

```bash
cp .env.example .env
```

Required values before boot:

| Variable            | Purpose                          | How to generate                                             |
|---------------------|----------------------------------|-------------------------------------------------------------|
| `SECRET_KEY`        | JWT signing + code fingerprinting | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `POSTGRES_PASSWORD` | TimescaleDB superuser password    | any strong random string                                     |
| `ADMIN_PASSWORD`    | initial admin account password    | any strong password (min 8 chars, 3+ character classes)      |
| `MQTT_CA_CERT` / `MQTT_CLIENT_CERT` / `MQTT_CLIENT_KEY` | mutual-TLS materials for MQTT (optional) | path to cert/key files |

> `SECRET_KEY` defaults to a fresh random value when unset, and the API refuses to start in
> `prod` with an empty/default key. Never reuse demo passwords in production.

## Manual steps before first boot

1. Generate a strong `SECRET_KEY` and put it in `.env` (command above). In production this must be a
   per-deployment random value kept secret.
2. Set `ENVIRONMENT=prod` and `DEBUG=false` in `.env` for production. The stack does **not** do this for you.
3. Set a strong `ADMIN_PASSWORD`. `db-init` seeds a default `admin` user idempotently — it only applies the
   password if the account doesn't exist yet.
4. (Optional) Provision EMQX mTLS certs and set `MQTT_CA_CERT`, `MQTT_CLIENT_CERT`, `MQTT_CLIENT_KEY`.

## Local development without Docker

Backend:

```bash
cd platform
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export POSTGRES_HOST=localhost # if running DB outside Docker
uvicorn fmp.api.main:app --reload --port 8000
```

Frontend:

```bash
cd web
npm install
npm run dev        # Vite on :5173, proxies /api + /ws to :8000
```

## Running tests

```bash
# Backend — unit + integration (integration requires postgres + redis running; see CI workflow)
cd platform && pytest -q

# Frontend — type-check + unit tests
cd web && npx tsc --noEmit && npx vitest run
```

## MQTT protocol

The edge ingestion engine expects well-defined MQTT topics and JSON payloads. Reference:
[`docs/mqtt-protocol.md`](docs/mqtt-protocol.md). The ESP32 firmware under [`firmware/`](firmware/)
implements this protocol end-to-end.

## Documentation index

| Document | What it covers |
|----------|----------------|
| [`docs/TECHNICAL_SPECIFICATION.md`](docs/TECHNICAL_SPECIFICATION.md) | overall spec |
| [`docs/architecture/SYSTEM_ARCHITECTURE.md`](docs/architecture/SYSTEM_ARCHITECTURE.md) | architecture + data flow diagrams |
| [`docs/architecture/ENTITY_RELATIONSHIP.md`](docs/architecture/ENTITY_RELATIONSHIP.md) | entity-relationship model |
| [`platform/docs/architecture/`](platform/docs/architecture/) | backend directory structure & dependencies |
| [`docs/mqtt-protocol.md`](docs/mqtt-protocol.md) | MQTT topics + payload schemas |
| [`docs/security/2026-XX-security-audit.md`](docs/security/) | security audit results |
| [`docs/archive/legacy-flask/`](docs/archive/legacy-flask/) | archived legacy Flask documentation (historical only) |