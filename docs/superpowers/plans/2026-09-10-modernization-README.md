# Modernization — SUB-1

The legacy Flask-era monolith (repo root: `app.py`, `k114_reader.py`, `models/`,
`blueprints/`, `services/mqtt_ingestion.py`, `templates/`, `static/`, old SQLite
migration scripts) was purged in SUB-1 of the architectural modernization.

The production stack is now entirely under `platform/` (FastAPI, `fmp/` package)
and `web/` (React SPA). See `platform/docs/superpowers/specs/2026-09-10-mqtt-ingestion-legacy-purge-design.md`.
