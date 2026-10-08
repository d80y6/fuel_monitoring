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

Devices were provisioned through the real path: rows in `iot_gateways` -> `mqtt-init` -> EMQX accounts
with per-device ACLs -> authenticated MQTT publish on `fuel/<mac>/readings`. No unauthenticated or
ACL-bypassing path was used. Provisioned devices were deleted and tank bindings restored afterwards.

### 4.1 What the first round got wrong, and what it revealed

An early round reported "46% delivered" and attributed the loss to broker flow control. That conclusion
was premature. Adding frame counters (see 4.3) showed the platform had **not** lost those frames — it was
queueing them and draining far too slowly. Two further defects were behind it:

| Defect | Symptom | Fix |
|---|---|---|
| Commit per frame inside the batch | A 500-frame batch took 100s; 344 frames in 2 minutes | Commit once per batch (`commit=False` per frame) |
| No savepoint per frame | A single bad frame would have discarded the whole batch | `session.begin_nested()` per frame confines the damage |

A third issue was found in the counters themselves: `frames_persisted` was incremented before the batch
commit, so a failed commit would have reported phantom deliveries. Accounting now happens only after a
successful commit.

### 4.2 Current measured behaviour

Final run: 1000 frames published by 4 devices at **394 fps**, unthrottled, QoS 1.

| Stage | Result |
|---|---|
| MQTT -> intake queue | **1000 / 1000** (344 processed + 656 queued at first observation) |
| Queue -> TimescaleDB | **1000 / 1000** persisted, queue drained to 0 |
| Intake-queue overflow | 0 |
| Pool errors | 0 |

**Ingestion is now lossless end to end** for this workload, which is the property that matters for a fuel
ledger. `frames_unaccounted` stayed at 0 throughout.

### 4.3 Throughput and its limit

Drain rate is the real capacity constraint, and it is **not** healthy:

| Observation | Value |
|---|---|
| Batch latency (500 frames) | 25.3 s - 100.9 s |
| Effective drain rate | ~11 - 20 frames/s |
| Offered load in the test | 394 fps |

At an offered load of ~394 fps the platform persists everything but does so by queueing, and the queue
would grow without bound under a sustained overload until it reaches its 50 000-frame bound and starts
dropping (now counted, and logged at `ERROR`).

The per-frame cost is dominated by work that is repeated for every frame rather than cached: strapping
lookup, alarm-rule evaluation with Redis round trips, company resolution, and the realtime publish. Batching
fixed the commit amplification but not the per-frame database and Redis chatter. **This is the top open
capacity risk** and needs a proper pass (per-tank memoisation of strapping and liveness, batched alarm
evaluation, batched realtime fan-out) before any capacity claim.

### 4.4 Frame accounting is now observable

`/api/v1/metrics` reports (admin-only):

```json
{"ingestion": {"available": true, "frames_received": 1000, "frames_persisted": 1000,
  "frames_rejected_no_tank": 0, "frames_dropped_queue_full": 0, "frames_unaccounted": 0,
  "delivery_ratio": 1.0, "queue_depth": 0, "batches": 4,
  "batch_latency_ms": 25295.5, "batch_latency_ms_max": 100855.5}}
```

`frames_unaccounted` is the operator's headline number: it should stay flat, and growth means telemetry is
being lost between broker and database. Counters live in Redis so they survive an ingestion restart and are
read by the API process, which is the one serving the endpoint. A fresh deployment reports zeros rather
than failing the endpoint.

## 5. Host conditions affecting these numbers

Two environmental factors degraded every measurement and must be corrected before sign-off:

- **Host was never idle.** Load per core ranged from ~4 to ~11 against 4 cores.
- **Disk was at 99% capacity** (`/` 145 GB, 1.8 GB free) for the whole exercise, largely from unrelated
  projects in `/home/ubuntu` (`~/.cache` 11 GB, `~/.local` 15 GB, plus several other project trees). A
  full disk inflates every commit and page fault, which is very likely why drain rate (4.3) and export
  latency are as poor as measured. This was not remediated: the space belongs to other projects and
  deleting it is not a decision this exercise should make unilaterally.

Two code-side contributions to the pressure were found and fixed: the image build context had no
`.dockerignore`, so `.mypy_cache`, `.pytest_cache`, `__pycache__` and `.venv` were being copied into the
image -- one image extract failed outright with `no space left on device`. The image is now 91 MB.

CPU, memory and container-restart behaviour under sustained load remain **uncharacterised**. Recording
that as unknown is the correct outcome.

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

1. **Re-run this harness on a dedicated, idle host with free disk** (load < 1.0/core, `df` > 20% free)
   and replace the upper-bound figures in §3 with real characteristics.
2. **Raise ingestion drain rate** (§4.3). At ~11–20 frames/s the platform cannot absorb realistic fleet
   bursts without growing its queue to the 50 000-frame drop bound. Needs per-tank memoisation of
   strapping/liveness, batched alarm evaluation, and batched realtime fan-out. This is the single largest
   open risk.
3. **Quantify the export optimisation** on a fixed dataset, and add streaming/pagination if it is still not
   acceptable for large tanks.
4. **Set and test a delivery target** for sustained overload, and decide publisher-side flow control vs
   broker-side buffering now that loss is measurable.
5. **Alert on the new counters** — `frames_unaccounted` and `queue_depth` should page, not just be visible
   in a JSON response.
6. **Characterise the resource envelope** (§5): sustained-load CPU, memory, and container restarts.

Items 2–5 are correctness/reliability items, not polish. Capacity sign-off should not be issued until
they are closed.