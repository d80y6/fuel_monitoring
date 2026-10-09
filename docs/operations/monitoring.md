# Monitoring and alerting

The platform drops telemetry under load. Until this existed, that was visible
only in a log line: no endpoint a scraper could read, and nothing that paged.

## Scrape endpoint

```
GET /api/v1/metrics/prometheus
```

Prometheus text exposition format (`text/plain; version=0.0.4`). Admin-only, like
`/api/v1/metrics` — it exposes fleet topology. `/api/v1/metrics` remains the
human-facing JSON view; both are computed from the same code path, so they cannot
disagree.

Metrics exposed:

| Metric | Meaning |
|---|---|
| `fuel_ingest_frames_received_total` | Frames accepted by the intake queue |
| `fuel_ingest_frames_persisted_total` | Frames written to TimescaleDB |
| `fuel_ingest_frames_unaccounted` | received − persisted − rejected. **Growth means loss.** |
| `fuel_ingest_frames_dropped_queue_full_total` | Frames discarded at the 50 000 queue bound |
| `fuel_ingest_queue_depth` | Frames waiting |
| `fuel_ingest_batch_latency_ms` / `_max` | Duration of the latest / slowest flush |
| `fuel_telemetry_receiving` | 1 when a reading arrived inside the staleness threshold |
| `fuel_telemetry_freshest_age_seconds` | Age of newest reading; −1 if none ever |
| `fuel_tanks_total` / `_offline` / `_stale` | Fleet state |
| `fuel_alarms_open` | Alarms active/acknowledged/escalated |

## Running the monitoring stack

Opt-in, because it competes for the same 4 CPUs the platform needs:

```bash
# one-time: create a metrics service account and put its token where prometheus reads it
docker compose exec -T api python -m fmp.scripts.create_metrics_token
docker compose --profile monitoring up -d prometheus alertmanager
```

- Prometheus: `http://localhost:9090` (add `-p 9090:9090` to publish it)
- Alertmanager: `http://localhost:9093`

Not started by default. On a small host, scraping plus rule evaluation makes the
ingestion latency numbers *worse*, so a monitoring stack bolted onto an already
oversubscribed box measures itself rather than the platform.

## Alert rules

`infra/prometheus/alerts.yml`. Every rule corresponds to a failure that has
actually occurred during development, not a hypothetical:

| Alert | Fires when |
|---|---|
| `FuelTelemetryFrameLoss` | `frames_unaccounted` increases — **the ledger is diverging from reality** |
| `FuelIngestQueueOverflow` | Frames dropped at the queue bound — unrecoverable loss |
| `FuelIngestQueueBacklog` | Queue above 5 000 for 10 min — drain rate below arrival rate |
| `FuelIngestBatchSlow` | Batch flush over 30 s — pipeline stalling |
| `FuelIngestCountersMissing` | No ingestion metrics — ingestion is not publishing |
| `FuelTelemetryStale` | Nothing arriving for 15 min |
| `FuelTelemetryNeverReceived` | Measurements table has never held a row |
| `FuelAllTanksOffline` | Every tank offline for 10 min |
| `FuelTanksGoingStale` | Over half the fleet stale for 30 min |
| `FuelAlarmsOpen` | Alarms left open for 30 min |

`test_alert_rules_cover_the_counters_we_expose` parses the rules and asserts
every metric they reference is actually exported, so a renamed metric cannot
leave a rule silently dead.

## Alert delivery

`infra/prometheus/alertmanager.yml` ships a null receiver — alerts are visible in
the Alertmanager UI but go nowhere. Wiring PagerDuty, Slack or email is an
operator decision and is left as a commented example rather than guessed at.

## Without Prometheus

The endpoint is plain HTTP, so anything can poll it:

```bash
TOKEN=$(curl -s -X POST http://localhost/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"admin\",\"password\":\"$ADMIN_PASSWORD\"}" \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

curl -s http://localhost/api/v1/metrics/prometheus -H "Authorization: Bearer $TOKEN"
```

For frame loss specifically, the signal to watch is `fuel_ingest_frames_unaccounted`
being non-zero and trending up. Anything else is a hiccup.