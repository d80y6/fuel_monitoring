# Production Readiness Report

**Date:** 2026-10-09 · commit `8cc8bda`
**Verdict: NOT READY for production. Conditionally ready for a controlled pilot with a named operator and a documented rollback.**

The distinction matters. The software is in better shape than it was, and its
core flows are verified working. What is missing is not features but the
evidence and operational scaffolding that make "production" a defensible claim.

---

## What is genuinely ready

- **Security.** Broker denies anonymous clients; per-device ACLs; dispensing and
  HTTP ingestion authenticated; TLS with mutual authentication on the broker,
  verified by confirming a certless MQTT CONNECT is refused; production refuses
  to start without TLS, a real signing key, a database password and debug off.
- **Tenancy.** Cross-tenant isolation holds across REST, WebSocket and reports.
  Verified with a dedicated test suite, not by inspection.
- **Correctness.** 371 backend tests and 288 frontend tests pass. Custom
  strapping, over-range handling, alarm auto-resolve, liveness, dispensing,
  reporting and CSV export were each exercised against the running stack.
- **Telemetry integrity.** A burst of 1000 frames persisted 1000/1000 with the
  queue draining to zero and zero unaccounted frames. Three genuine
  data-loss defects on this path were found and fixed during verification.

## Why it is not production-ready

### 1. No capacity number (blocking)

Every latency figure recorded is an **upper bound from a contended host** — load
20–26 across 4 cores, disk at 99%. A bare `SELECT 1` from the application
container costs ~57 ms there, which caps ingestion at a few frames per second
regardless of the code. The code-level work is real and verified (0.08 SQL
statements per frame, down from ≥2), but **the platform's actual capacity is
unknown**. Signing off a production SLA on this data would be guessing.

Owner action: re-run `scripts/measure_performance.py` on a dedicated idle host
and record the result in `docs/operations/performance-capacity-report.md`.

### 2. No browser-level verification (blocking)

Nothing in this repository opens a browser. Every frontend result comes from
Vitest, `tsc` and a production build. Untested: render errors, keyboard and
focus behaviour, screen-reader semantics, responsive breakpoints, and the Arabic
RTL layout — which is a *visual* property and cannot be validated by a jsdom
test that only asserts `<html dir="rtl">` exists.

Owner action: add Playwright smoke coverage of login → tanks → tank detail →
alarms → reports, in both LTR and RTL.

### 3. Ingestion throughput unproven (blocking)

Delivery is lossless and round trips are minimal, but a sustained fleet load has
never been applied. The intake queue is bounded at 50 000 frames; when it fills,
frames are dropped (now counted and alerted, but still dropped). Whether a real
fleet's arrival rate stays under the drain rate is **unknown**.

Owner action: a sustained-load soak on adequate hardware with an explicit
delivery target.

### 4. Alerting does not reach anyone

Rules exist and the counters are scrapeable, but Alertmanager ships a null
receiver. A fuel ledger losing frames would currently page nobody.

Owner action: point Alertmanager at a real destination and prove a test alert
fires end to end.

### 5. No backup, restore or HA

Single host. No backup schedule, no restore test, no redundancy. Host failure is
total loss of the ledger. For a system whose value is historical fuel accounting,
this is the most consequential omission on the list.

Owner action: define RPO/RTO, implement automated backups, **restore into a clean
environment and prove the data comes back**, then decide on topology.

### 6. Secret rotation is undocumented

TLS material and the broker API key can be generated, but there is no runbook.
Rotating the broker key re-provisions every device account; rotating the CA
disconnects all of them. An operator doing this under pressure will cause an
outage.

### 7. Bilingual coverage is partial

7 of 21 pages are translated. An Arabic user reaches a working app and then hits
English walls mid-workflow — a worse experience than no Arabic at all, and a
correctness risk if someone operates a site in Arabic and misreads a label.

---

## Deployment checklist (for a pilot)

Do these before pointing real devices at it:

1. Set `ENVIRONMENT=prod` and confirm the service starts — it will refuse if
   TLS, `SECRET_KEY`, `POSTGRES_PASSWORD` or `DEBUG` are wrong.
2. Run `scripts/generate_certs.sh`; do not reuse the development CA.
3. Issue device certificates if devices must present one; otherwise accept that
   `fuel/<mac>/#` over TLS is protected by credentials alone on port 1883.
4. Wire Alertmanager to a destination and trigger a test alert.
5. Enable Prometheus scraping and confirm `fuel_ingest_frames_unaccounted` is
   visible before trusting the system.
6. Implement backups and **test a restore**.
7. Re-run the performance harness on the target hardware and record real numbers.
8. Decide the pilot's blast radius: which sites, how many devices, and what
   happens if ingestion falls behind.

## What would change the verdict

**Pilot-ready** when: browser smoke tests pass in LTR and RTL, a real capacity
number exists for the target hardware, and alert delivery is proven.

**Production-ready** additionally requires: sustained-load soak passing a stated
delivery target, tested backup/restore, and a documented rotation runbook.

None of these are large engineering tasks. All of them are prerequisites for
saying "ready" honestly.

---

## Honest summary

The gap between "the code works" and "this is production-ready" is mostly
verification and operations, not functionality. That is a much better position
to be in, and it is also a position where overclaiming is easy — which is why
this report says not ready rather than attaching a percentage.