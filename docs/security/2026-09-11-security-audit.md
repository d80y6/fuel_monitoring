# Security Audit — 2026-09-11

**Scope:** fuel-monitoring platform — `platform/fmp` (FastAPI + TimescaleDB + Redis),
`web/` (React + Vite), `infra/`, `docker-compose.yml`, and the new ESP32 edge
firmware (`firmware/`). Code-level audit of the current working tree.

**Method:** source review with `file:line` evidence; NOT a penetration test.
Findings are reproducible by inspecting the referenced locations.

---

## Controls audit summary

| # | Control area | Status | Key evidence |
|---|--------------|--------|--------------|
| 1 | JWT issuance (HS256, `sub/iat/exp/jti/iss/aud`, role in claims) | GOOD | `platform/fmp/core/security.py:62-74` |
| 2 | JWT validation (iss/aud required, alg pinned, required claims) | GOOD | `platform/fmp/core/security.py:77-90` |
| 3 | Constant-time credential check + active-user check | GOOD | `platform/fmp/services/auth.py:29-65` |
| 4 | RBAC guards (`CurrentUser`/`PrivilegedUser`/`AdminUser`) | GOOD | `platform/fmp/api/deps.py:16-58` |
| 5 | Refresh-token / token-revocation flow | GAP | `REFRESH_TOKEN_EXPIRE_DAYS` ever-unused (`config.py:34`); no `/refresh`; stateless JWTs documented in `api/v1/auth.py:133-136` |
| 6 | Login rate limiting (5 / 900 s, username+IP key, no fail-open) | GOOD | `api/v1/auth.py:42-116`, `core/redis.py:59-73`, `tests/unit/test_security.py:125-142` |
| 7 | Password policy (≥8 chars, ≥3/4 classes, PBKDF2-SHA256 210k iters) | GOOD | `core/security.py:23-43,93-110`; `config.py:35` |
| 8 | WS auth (JWT on query string; no active-user DB check) | RISK | `api/v1/realtime.py:18-68`; `security.py:113-122` |
| 9 | CORS (explicit origins, credentials + wildcard methods/headers) | GAP | `api/main.py:38-44`; `config.py:106`; origins are dev-only |
| 10 | Security headers (CSP, XFO, nosniff, HSTS, Referrer-Policy) | GAP | nginx only: `infra/nginx/conf.d/app.conf:10-16`; **none at ASGI layer** |
| 11 | HTTPS/TLS termination | GAP | nginx listens plain `:80` only (`app.conf:2`); HSTS header ineffective |
| 12 | DB (Postgres/TimescaleDB) | GOOD | DB never published to host (`docker-compose.yml:14-27`); risk limited to weak default creds |
| 13 | Redis | GAP* | no password, but not published to host (`docker-compose.yml:29-39`) |
| 14 | MQTT broker (EMQX) | RISK | no auth source, `no_match=allow`, dashboard/TLS ports open (`infra/emqx/emqx.conf`; `docker-compose.yml:45-49`) |
| 15 | Secret management (`.env` gitignored, env_file pattern) | GOOD | `.gitignore:4`, `docker-compose.yml` `env_file` blocks |
| 16 | Secrets hygiene (default creds live) | RISK | `.env` carries known `ADMIN_PASSWORD` + DB creds; compose has inline defaults |
| 17 | Sensitive-data logging | GOOD | 0 hits for password/token/secret logging in `platform/fmp/` |
| 18 | Malformed-sensor-frame resilience | GOOD | parse guards + per-tank isolation in `ingestion/pipeline.py:232-233`, `ingestion/main.py:168-169` |
| 19 | CI dependency audit | GOOD | pip-audit + npm audit in `.github/workflows/ci.yml:71-74,102-103` |

\* mitigated by network isolation; real risk materializes only if Redis host exposure is added.

---

## Findings

### F1 — Unauthenticated dispense endpoints (HIGH)
`platform/fmp/api/v1/dispensing.py` exposes `POST /upload` (:40), `POST /validate` (:76),
`POST /complete` (:85) and `POST /upload/{batch}/dispatch` (:94) **without any
`CurrentUser`/`PrivilegedUser` dependency**; only the list endpoints (120, 143) require auth.

- Impact: quota upload, code validation and dispense settlement are reachable by
  anyone who can reach the API host.
- Evidence: router handlers carry no auth dependency.
- Recommendation: gate `/validate`, `/complete`, `/upload`, `/dispatch` behind
  `PrivilegedUser`; validate at review before merge.

### F2 — EMQX broker: anonymous access, no TLS (HIGH)
`infra/emqx/emqx.conf` sets `authorization.no_match = "allow"` with only an empty
`built_in_database` source. No authentication source is configured. `1883`, `8883`,
`8083` (WS) and `18083` (dashboard) are all published to the host (`docker-compose.yml:45-49`).
The platform ingestion client connects plaintext `:1883` with no credentials
(`ingestion/main.py:58-61`).

- Impact: any network peer can publish to `fuel/+/readings`, `ingestion/dispense/*`
  and subscribe to command topics; telemetry + dispense-control plane are exposed.
- Evidence: `emqx.conf:23-33`; `docker-compose.yml:45-49`; `ingestion/main.py:61-74`.
- Recommendation: enable `authentication` (username/password or configured-X.509 /
  mTLS via EMQX Enterprise), set `authorization.no_match = "deny"`, ACL the device
  topics per gateway, remove the host publication of `18083`, and wire the ingestion
  client to `:8883` with TLS + credentials.

### F3 — Known default admin credential, no forced rotation (HIGH)
`.env` ships `ADMIN_USERNAME=admin`, `ADMIN_PASSWORD=Admin@1234` (also used in tests).
The seed is idempotent and refuses weak passwords (`scripts/seed_admin.py:31-70`),
but `ADMIN_FORCE_PASSWORD` defaults `False` (`core/config.py:103`) and is **not set**
in `.env`, so a deployed instance keeps the known credential unless manually rotated.

- Impact: trivial admin takeover on any instance deployed with the default `.env`.
- Evidence: `.env:59-60`; `config.py:103`.
- Recommendation: set a strong non-default password in `.env` before first boot,
  or `ADMIN_FORCE_PASSWORD=true` with a generated password; document rotation in
  the ops runbook.

### F4 — Weak default DB/Redis creds (MEDIUM)
Compose has inline fallbacks `fuel_platform`/`fuel_platform` for POSTGRES
(`docker-compose.yml:18-20`) and `config.py:44-45` carries `fuel_user`/`fuel_pass`
fallbacks. Redis runs with no password but is not host-published.

- Impact: low while DB/Redis stay on the internal docker network; becomes critical
  if port mapping is ever added.
- Evidence: `docker-compose.yml:18-20,32`; `core/config.py:44-45,55`; `.env:21-30`.
- Recommendation: rotate all DB/Redis credentials; add a Redis password; remove the
  `fuel_user`/`fuel_pass` fallbacks from `config.py`.

### F5 — JWT exposure: localStorage + WS query string (MEDIUM)
The access token is persisted in `localStorage` (`web/src/store/auth.ts:35`) and is
passed on WebSocket URLs in the query string (`web/src/hooks/useTelemetrySocket.ts:14-16`,
JWT parsed in `security.py:113-122`). uvicorn runs with default access-logging enabled.

- Impact: token readable by any XSS; WS token can leak into access logs / proxies.
- Evidence: `web/src/store/auth.ts:35`; `useTelemetrySocket.ts:14-16`;
  `docker-compose.yml` uvicorn commands (no `--no-access-log`).
- Recommendation: move WS auth to a dedicated short-lived one-time ticket channel or
  negotiated cookie at connect time; add `--no-access-log`; mitigate XSS via existing
  CSP `script-src 'self'`.

### F6 — No refresh/revocation flow (MEDIUM)
Access tokens (60-min TTL, `config.py:33`) are stateless and never denylisted;
`REFRESH_TOKEN_EXPIRE_DAYS` is dead config. Logout clears client storage only.

- Impact: a stolen token is valid for up to 60 min; users can't be force-logged-out.
- Evidence: `config.py:33-34`; `api/v1/auth.py:133-136`.
- Recommendation: add refresh-token rotation with server-side denylist/revocation,
  or lower access TTL and issue per-device session records.

### F7 — WS connections not re-validated against active users (MEDIUM)
`api/v1/realtime.py` verifies JWT signature/iss/aud but does not confirm the user
still exists/active in DB, unlike the REST path.

- Evidence: `api/v1/realtime.py:18-34,59-68`; `security.py:113-122`.
- Recommendation: assert active user (+ role) at WS connect, matching
  `services/auth.py`.

### F8 — No TLS termination anywhere (MEDIUM)
nginx serves plain HTTP on `:80` only; HSTS is set (`app.conf:16`) but ineffective
without HTTPS. `CORS_ORIGINS` are dev-only (`config.py:106`).

- Evidence: `app.conf:2,16`; `web/nginx.conf`.
- Recommendation: terminate TLS on the host resolver or a reverse proxy, add a
  Let's Encrypt/corporate CA flow, and configure the server-side certificate.

### F9 — Ingest fallback endpoints unauthenticated & effectively unreachable (MEDIUM)
`ingestion/main.py` `POST /api/v1/ingest/backfill` (:337) and `POST /api/v1/ingest/readings`
(:326) are unauthenticated. They are internal-only (port 8001 not host-published),
but the docs'/firmware fallback `POST /api/v1/ingest/backfill` maps through the ngines
`/ingest/` vhost (`app.conf:36-41`) to the API `:8000` which has **no such route**
(grep: 0 hits in `fmp/api`), so the HTTP fallback 404s externally.

- Impact: offline-buffer HTTPS fallback does not exist as documented; internal
  endpoints accept spoofed readings without auth.
- Evidence: `ingestion/main.py:326-348`; `app.conf:36-41`; `docs/mqtt-protocol.md` §8.
- Recommendation: add a shared-secret/device-key header to ingest endpoints; expose
  the intent fallback via a nginx route that reaches `ingest:8001`, or document MQTT
  replay as the only transport.

### F10 — EMQX dashboard + node cookie (LOW)
Dashboard creds are never pinned in config and the node cookie is hardcoded
(`emqx.conf:11`). Open dashboard is host-published.

- Evidence: `infra/emqx/emqx.conf:11,14-16`; `docker-compose.yml:49`.
- Recommendation: remove `18083` host publication; set a random cookie; pin
  dashboard auth externally (admin_secret or reverse proxy).

---

## What is in good shape

- JWT path: pinned HS256, required claim set with `iss`/`aud` enforcement,
  constant-time password compare, PBKDF2-SHA256 @ 210k iterations.
- Login rate limiting is on-by-default, keyed by username+IP, and does not fail open.
- RBAC guards used consistently across all CRUD routers outside dispensing.
- Secrets are injected via gitignored `.env` (not committed).
- No credential/token logging anywhere in `platform/fmp`.
- Malformed MQTT frames are dropped without crashing the pipeline.
- CI enforces `pip-audit` and `npm audit`.

## Recommended remediation order

1. **F1, F2** — dispense authn gates; EMQX auth + deny-by-default.
2. **F3** — rotate admin credential, force via `ADMIN_FORCE_PASSWORD`.
3. **F5, F7** — WS auth hardening; `--no-access-log`.
4. **F4** — rotate DB/Redis creds; add Redis password.
5. **F6, F8, F9, F10** — refresh/revocation, TLS termination, ingest fallback, EMQX dashboard.