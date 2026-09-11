# Modernization — SUB-1

The legacy Flask-era monolith (repo root: `app.py`, `k114_reader.py`, `models/`,
`blueprints/`, `services/mqtt_ingestion.py`, `templates/`, `static/`, old SQLite
migration scripts) was purged in SUB-1 of the architectural modernization.

The production stack is now entirely under `platform/` (FastAPI, `fmp/` package)
and `web/` (React SPA). See `platform/docs/superpowers/specs/2026-09-10-mqtt-ingestion-legacy-purge-design.md`.

## SUB-2: IoT gateway command API (2026-09-11)

Adds `iot_gateways` + `gateway_commands` tables and a durable, ack-tracked
command plane: API-issued commands ride a Redis list into the ingestion relay,
publish to `fuel/{mac}/command`, and are confirmed on `fuel/{mac}/command/ack`.
Heartbeats auto-register gateways; admin links tanks to provision them. Celery
beat sweeps expired sends with exponential backoff then marks failed. Frontend
console at `/admin/iot-gateways`. Spec:
`docs/superpowers/specs/2026-09-11-iot-gateway-command-api-design.md`.
