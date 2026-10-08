# Performance and Capacity Report

**Date:** 2026-10-08
**Stack under test:** `docker compose` on a single host — 4 vCPU, 8 GB RAM, TimescaleDB 2.11/PostgreSQL 14,
EMQX 5.8.6, Redis 7, 1 API container (2 uvicorn workers), 1 ingestion container, 1 Celery worker
(`--concurrency=4`), 1 Celery beat.

All figures below are **measured**, not modelled. Where a number could not be measured honestly it is
recorded as such rather than estimated.

---

## 1. Measurement integrity warning

The host running this measurement is **not** dedicated to the platform. Two distinct host states were
observed during the exercise, and they are reported separately because they change the meaning of every
latency number:

| Phase | Load average (1/5/15 min) | Load per core | Meaning |
|---|---|---|---|
| Initial runs | ~45 | ~11.4/core | Host badly oversubscribed by an unrelated workload |
| Final run | 16.08 | 4.02/core | Much improved, still oversubscribed |

**No run achieved an idle host** (load < 1.0/core). Every latency figure below is therefore an **upper
bound inflated by CPU contention** and must not be treated as a platform characteristic. A capacity
sign-off on a quiet, dedicated host is still outstanding; see §7.

`scripts/measure_performance.py` records host load on every run and prints an explicit warning when
`load_per_cpu >= 1.0`, so a contaminated run cannot be mistaken for a clean one.

---

## 2. Defects found and fixed during this exercise

Performance testing surfaced three genuine production defects. All three were fixed, covered by tests,
and deployed.

### 2.1 Ingestion connection-pool exhaustion (data loss under burst)

**Severity: critical.** Ingestion opened one SQLAlchemy session per MQTT message
(`fmp/ingestion/main.py::_handle_reading`). With `pool_size=20, max_overflow=20`, a burst delivering
~40 concurrent frames exhausted the pool and **every subsequent frame failed**:

```
sqlalchemy.exc.TimeoutError: QueuePool limit of size 20 overflow 20 reached,
connection timed out, timeout 30.00
```

Telemetry was silently discarded — the frames were dropped, not queued. This was found while measuring
ingestion, not by inspection.

**Fix:** reading frames are now handed to a bounded intake queue and drained in batches of 500 every
500 ms over a **single** pooled connection (`_enqueue_reading` / `_flush_readings`). The queue is bounded
at 50 000 frames; overflow is counted and logged at `ERROR` rather than discarded silently. Other
message classes (dispensing, status, command acks) keep their own short-lived sessions because they are
low-frequency and order-sensitive.

**Coverage:** `platform/fmp/tests/unit/test_ingestion_backpressure.py` (5 tests) asserts that queueing
opens no session, that a 250-frame burst uses exactly one connection, that a bad frame does not take
its batch down with it, that overflow is reported, and that a shared session is only opened when none
was supplied.

### 2.2 Unbounded in-memory growth in the telemetry pipeline

**Severity: high.** `IngestionPipeline` appended every processed reading to `self._pending`, and nothing
ever read or cleared it (`pipeline.py`). It was write-only state — a slow memory leak that would
eventually OOM the ingestion process in a long-running deployment. The list was removed; rows were
already being inserted synchronously.

### 2.3 Health checks that reported healthy services as unhealthy

Three health checks failed under CPU starvation for reasons unrelated to service health, which makes a
capacity assessment untrustworthy — an operator would restart a healthy broker.

| Service | Was | Cause | Now |
|---|---|---|---|
| `emqx` | `emqx ctl status \| grep 'is started'`, 25 s budget | Spawns an Erlang RPC node; times out under load | Listening-socket check on `/proc/net/tcp` (`:075B … 0A`), 10 s |
| `worker` | `celery inspect ping`, 20 s budget | Full client process: app import + broker round trip | 90 s budget, `start_period` 90 s |
| `api`, `ingest` | Python probe, 5 s budget | Interpreter startup alone consumed the budget | 20 s budget |

The EMQX probe is now strictly cheaper and strictly more meaningful (it answers "is the broker accepting
clients", which is the property Compose actually depends on).

---

## 3. API read latency (measured)

10 repeats per endpoint, same authenticated admin session, nginx entry point.

| Endpoint | Status | Median | p95 | Max |
|---|---|---|---|---|
| tank list | 200 | 268.0 ms | 2861.7 ms | 2861.7 ms |
| tank detail | 200 | 212.0 ms | 264.9 ms | 264.9 ms |
| telemetry recent | 200 | 429.7 ms | 607.1 ms | 607.1 ms |
| telemetry range 24h/5min | 200 | 380.2 ms | 549.4 ms | 549.4 ms |
| telemetry range 7d/1hour (aggregate) | 200 | 313.6 ms | 551.3 ms | 551.3 ms |
| telemetry export 24h | 200 | 1641.5 ms | 4197.8 ms | 4197.8 ms |
| consumption analytics | 200 | 130.0 ms | 255.3 ms | 255.3 ms |
| alarm list | 200 | 151.8 ms | 489.4 ms | 489.4 ms |
| report: tank inventory | 200 | 209.2 ms | 377.8 ms | 377.8 ms |
| report: consumption | 200 | 169.9 ms | 238.1 ms | 238.1 ms |
| report: alarms | 200 | 165.8 ms | 252.0 ms | 252.0 ms |
| report: dispensing audit | 200 | 79.9 ms | 164.7 ms | 164.7 ms |

Observations:

- Report endpoints are the fastest class (80–210 ms median) — reporting was built as one calculation path
  shared by JSON and CSV, so this is expected rather than lucky.
- **`telemetry export 24h` is the clear outlier**: 1.64 s median, 4.20 s max, ~4× the slowest read path.
  It serialises every row in the window; it needs streaming/pagination before it is fit for large tanks.
- `tank list` shows a 2.9 s p95 against a 268 ms median, i.e. a heavy tail rather than a uniformly slow
  endpoint. With load 4.0/core that tail is most likely contention, and must be re-measured.
- An earlier run of the same harness returned `422` on every timestamp-parameterised endpoint. That was a
  **bug in the harness**, not the API: `+00:00` in a query string is decoded as a space. The script now
  emits UTC `Z`-suffixed timestamps.

---

## 4. Telemetry ingestion (measured)

Devices were provisioned through the real path: rows in `iot_gateways` → `mqtt-init` → EMQX accounts with
per-device ACLs → authenticated MQTT publish on `fuel/<mac>/readings`. No unauthenticated or ACL-bypassing
path was used. Provisioned devices were deleted and tank bindings restored afterwards.

| Offered load | Devices | Frames | Client-side rate | Delivered |
|---|---|---|---|---|
| Throttled | 1 | 200 @ 20 fps | 20 fps | ~100% |
| Unthrottled | 4 | 800 | 132 fps | ~46% |
| Unthrottled | 4 | 1000 | 105 fps | ~46% |

Interpretation, stated precisely:

- At a rate a single device can sustain (20 fps), delivery is complete.
- Under an **unthrottled** burst the platform persisted only ~46% of frames. With the connection-pool
  defect fixed there were **zero** `QueuePool` errors and **zero** intake-queue overflows, so the loss is
  **not** in the database layer. Timestamps that did arrive were unique, confirming the
  `ON CONFLICT (tank_id, timestamp)` guard is not the cause.
- The remaining loss is therefore broker/client flow control: paho defaults (`max_inflight_messages=20`)
  plus EMQX's per-session queue, with no publisher-side rate limiting and no persistent session on the
  ingestion client (`client_id` is randomised per start, so `clean_session` is in effect). Under
  overload the broker drops rather than buffering.
- **This is a real production characteristic and not yet a defect-free configuration.** Sustained-rate
  behaviour is sound; burst behaviour needs either publisher-side flow control (recommended — an ATG or
  RTU must respect inflight limits) or broker-side buffering (`max_mqueue_len`, persistent sessions).

Frame loss is visible to an operator: the queue-overflow counter is logged at `ERROR`, and `/readyz`
reflects dependency health. It is *not* currently surfaced as a Prometheus counter — see §7.

---

## 5. Resource envelope

Not measured to a defensible standard. The host never fell below 4.0 load/core, so CPU, memory and
container-restart behaviour under sustained load were **not** characterised. Recording this as unknown is
the correct outcome; guessing a figure here would be worse than leaving it blank.

---

## 6. Verification state after these changes

| Check | Result |
|---|---|
| `ruff check fmp/` | clean |
| Backend suite (`pytest -q`, CI-equivalent env) | **368 passed**, 2 pre-existing deprecation warnings |
| New backpressure tests | 5 passed |
| `compose ps` | all 10 services healthy |
| `/api/v1/readyz` | `{"status":"ready","failed":[],"checks":{"database":{"ok":true},"redis":{"ok":true},"mqtt":{"ok":true}}}` |
| Ingest pool errors during burst | 0 |
| Ingest intake-queue overflows during burst | 0 |

**Known test-environment caveat:** `test_sweeper_requeues_then_fails` fails when the suite is run against
the *live* stack, because the running Celery worker's command relay consumes the same Redis key
(`QUEUE_OUTBOUND`) the test asserts on. Verified by stashing the changes and re-running: it fails
identically on pristine `HEAD`, so it is environment cross-talk, not a regression. CI uses an isolated
Redis and is unaffected.

---

## 7. Outstanding work before capacity sign-off

1. **Re-run this harness on a dedicated, idle host** (load < 1.0/core) and replace the upper-bound figures
   in §3 with real characteristics.
2. **Fix or formally accept the `telemetry export 24h` path** (1.64 s median / 4.20 s max). It needs
   streaming or pagination to be acceptable for large tanks.
3. **Decide the burst-tolerance policy** — publisher-side flow control, or EMQX buffering with persistent
   sessions. Then re-run the unthrottled burst and require a stated delivery target.
4. **Characterise the resource envelope** (§5): sustained-load CPU, memory, and whether the ingestion
   container restarts.
5. **Expose ingestion health as metrics** — queue depth, overflow count, and frames persisted vs received
   as counters on `/api/v1/metrics`, so silent loss becomes alertable rather than log-only.
6. **Fix the deployment path for `infra/emqx/api_keys.txt`** — the file is git-ignored but Compose
   bind-mounts it unconditionally, so a clean checkout fails to start. Provisioning instructions must
   create it first, or the mount must become optional.

Items 2–6 are correctness/reliability items, not polish. Capacity sign-off should not be issued until
they are closed.