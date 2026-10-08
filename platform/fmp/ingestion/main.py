"""Edge Ingestion Engine — standalone FastAPI service on :8001.

Consumes dispenser telemetry + dispense intents from the EMQX MQTT broker
and hands the security-critical operations to the Dispense Engine.

Wire protocol (JSON, schema-validated at the broker):
* ingestion/readings            – tank level sensor frames → TimescaleDB
* ingestion/status              – station heartbeats & diagnostics
* ingestion/dispense/validate   – authorization intent → validate_code()
* ingestion/dispense/complete   – settled dispense → complete_dispense()
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import ssl
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import Depends, FastAPI
from paho.mqtt.client import CallbackAPIVersion
from paho.mqtt.client import Client as MqttClient
from sqlalchemy import select

from fmp.core.config import get_settings
from fmp.core.database import async_session_factory
from fmp.core.device_auth import require_ingest_key
from fmp.core.logging_setup import configure_logging
from fmp.core.redis import RedisClient
from fmp.ingestion import metrics_counters as _counters
from fmp.ingestion.pipeline import IngestionPipeline, publish_live
from fmp.ingestion.relay import parse_command_ack_topic
from fmp.schemas.dispensing import CodeValidateRequest, DispenseCompleteRequest
from fmp.schemas.telemetry import BackfillBatch, IngestOutcome, TelemetryFrame
from fmp.services.dispensing.dispense_engine import complete_dispense, validate_code

configure_logging()
logger = logging.getLogger("ingestion")
settings = get_settings()

_loop: asyncio.AbstractEventLoop | None = None
_client: MqttClient | None = None


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    global _loop, _client

    from fmp.ingestion.batch_writer import ensure_hypertables
    from fmp.ingestion.tsdb_policies import ensure_timescale_policies

    async with async_session_factory() as session:
        try:
            await ensure_hypertables(session)
            await ensure_timescale_policies(session)
        except Exception:  # noqa: BLE001 — telemetry still works without TS
            logger.warning("hypertable/policy bootstrap skipped (is TimescaleDB enabled?)")

    _loop = asyncio.get_running_loop()
    _flusher = asyncio.create_task(_flush_readings(), name="reading-batch-flusher")
    _client = _build_client()
    _client.on_message = _on_message
    _client.on_connect = _on_connect
    _client.connect_async(settings.MQTT_BROKER, settings.MQTT_PORT, settings.MQTT_KEEPALIVE)
    _client.loop_start()
    await _wait_connected(_client)
    _client.subscribe(
        [
            ("ingestion/readings", settings.MQTT_QOS),
            ("ingestion/status", settings.MQTT_QOS),
            ("ingestion/dispense/validate", settings.MQTT_QOS),
            ("ingestion/dispense/complete", settings.MQTT_QOS),
            ("fuel/+/readings", settings.MQTT_QOS),
            ("fuel/+/status", settings.MQTT_QOS),
            ("fuel/+/command/ack", settings.MQTT_QOS),
        ]
    )
    logger.info(
        "MQTT subscription active on %s:%s", settings.MQTT_BROKER, settings.MQTT_PORT
    )
    from fmp.ingestion.relay import command_relay_loop

    relay_task = asyncio.create_task(command_relay_loop(_client))
    try:
        yield
    finally:
        _flusher.cancel()
        try:
            await _flusher
        except (asyncio.CancelledError, Exception):  # noqa: B014 — shutdown is best effort
            pass
    relay_task.cancel()
    _client.loop_stop()
    _client.disconnect()


app = FastAPI(
    title="Edge Ingestion Engine",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)


#: In-process dead-letter ring: frames rejected after broker authentication.
#: Bounded so a misbehaving device cannot grow the process unboundedly.
DEAD_LETTER_MAX = 500
_dead_letters: list[dict[str, Any]] = []


def _dead_letter(gateway_mac: str, kind: str, payload: dict[str, Any], reason: str) -> None:
    """Record a rejected frame with the reason it could not be applied (G-115)."""
    entry = {
        "at": datetime.now(UTC).isoformat(),
        "gateway_mac": gateway_mac,
        "kind": kind,
        "reason": reason,
        "payload_keys": sorted(payload.keys()),
    }
    _dead_letters.append(entry)
    del _dead_letters[:-DEAD_LETTER_MAX]
    logger.warning("dead-letter %s from %s: %s", kind, gateway_mac, reason)


def dead_letters() -> list[dict[str, Any]]:
    """Recent rejected frames (newest last) for operators and tests."""
    return list(_dead_letters)


def parse_fuel_topic(topic: str) -> tuple[str, str, None] | None:
    """Parse fuel/<gateway_mac>/<kind> → (gateway_mac, kind, None)."""
    parts = topic.split("/")
    if len(parts) == 3 and parts[0] == "fuel" and parts[2] in ("readings", "status"):
        return parts[1], parts[2], None
    return None


async def _wait_connected(client, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if client.is_connected():
            return
        await asyncio.sleep(0.2)
    raise ConnectionError("MQTT broker never became available")


def _build_client() -> MqttClient:
    """MQTT client authenticated against the broker (G-001).

    The broker is deny-by-default, so a client without credentials is rejected at
    CONNECT and no telemetry flows. TLS is enabled whenever a CA bundle is
    configured, which is the production expectation.
    """
    client = MqttClient(
        CallbackAPIVersion.VERSION2,
        client_id=f"fuel-platform-ingest-{uuid.uuid4().hex[:8]}",
    )
    if settings.MQTT_TLS_PORT and settings.MQTT_CA_CERT:
        client.tls_set(
            ca_certs=settings.MQTT_CA_CERT,
            certfile=settings.MQTT_CLIENT_CERT,
            keyfile=settings.MQTT_CLIENT_KEY,
            tls_version=ssl.PROTOCOL_TLS_CLIENT,
        )
    if settings.MQTT_SERVICE_USERNAME:
        client.username_pw_set(
            settings.MQTT_SERVICE_USERNAME, settings.MQTT_SERVICE_PASSWORD
        )
    else:
        logger.warning(
            "MQTT_SERVICE_USERNAME is not set; the broker denies anonymous clients, so this "
            "service will not receive telemetry until broker credentials are provisioned"
        )
    return client


def _on_connect(client, userdata, flags, reason_code, properties):
    if getattr(reason_code, "is_failure", False) or int(getattr(reason_code, "value", 0) or 0) >= 128:
        logger.error("MQTT connection refused by broker: %s", reason_code)
    client.subscribe(
        [
            ("ingestion/readings", settings.MQTT_QOS),
            ("ingestion/status", settings.MQTT_QOS),
            ("ingestion/dispense/validate", settings.MQTT_QOS),
            ("ingestion/dispense/complete", settings.MQTT_QOS),
            ("fuel/+/readings", settings.MQTT_QOS),
            ("fuel/+/status", settings.MQTT_QOS),
            ("fuel/+/command/ack", settings.MQTT_QOS),
        ]
    )


def _on_message(client, userdata, msg) -> None:  # paho runs this on its own thread
    try:
        payload: dict[str, Any] = json.loads(msg.payload)
    except (json.JSONDecodeError, TypeError):
        logger.warning("dropped malformed frame on %s", msg.topic)
        return
    assert _loop is not None
    asyncio.run_coroutine_threadsafe(_route(msg.topic, payload), _loop)


async def _route(topic: str, payload: dict[str, Any]) -> None:
    redis = RedisClient()
    try:
        if topic == "ingestion/dispense/complete":
            req = DispenseCompleteRequest(**payload)
            async with async_session_factory() as session:
                result = await complete_dispense(session, redis, req)
            logger.info("dispensed status=%s", result.status)
        elif topic == "ingestion/dispense/validate":
            req = CodeValidateRequest(**payload)
            async with async_session_factory() as session:
                result = await validate_code(session, redis, req)
            logger.info("validated ok=%s reason=%s", result.valid, result.reason)
        elif topic.startswith("fuel/") and topic.endswith("/command/ack"):
            mac = parse_command_ack_topic(topic)
            if mac is None:
                logger.warning("dropped malformed ack topic %s", topic)
            else:
                await _handle_command_ack(redis, payload, mac)
        elif topic.startswith("fuel/"):
            parsed = parse_fuel_topic(topic)
            if parsed is None:
                logger.warning("dropped malformed fuel topic %s", topic)
                return
            gateway_mac, kind, _ = parsed
            if kind == "status":
                await _handle_status(redis, payload, gateway_mac)
            else:
                _enqueue_reading(payload, gateway_mac)
        elif topic.startswith("ingestion/readings"):
            await _handle_reading(redis, payload)
    except Exception:  # noqa: BLE001 — a bad frame must not kill the loop
        logger.exception("failed to process frame on %s", topic)
    finally:
        await redis.client.aclose()


pipeline = IngestionPipeline(write_batch=True)


@contextlib.asynccontextmanager
async def _session_scope(db_session=None):
    """Yield ``db_session`` when the batch flusher already owns one.

    Opening a session per frame exhausted the QueuePool (size 20 + overflow 20)
    at ~40 concurrent frames and silently dropped telemetry, so reading frames
    are now drained in batches over a single connection.
    """
    if db_session is not None:
        yield db_session
    else:
        async with async_session_factory() as owned:
            yield owned


async def _handle_reading(
    redis: RedisClient, payload: dict[str, Any], *, gateway_mac: str | None = None
) -> None:
    """Persist a single reading on its own connection (HTTP/direct callers)."""
    await _process_reading(None, redis, payload, gateway_mac=gateway_mac)


async def _process_reading(
    db_session,
    redis: RedisClient,
    payload: dict[str, Any],
    *,
    gateway_mac: str | None = None,
    commit: bool = True,
) -> None:
    """Persist a tank sensor frame and fan it out to the realtime channel.

    ``commit=False`` lets the batch flusher accumulate many frames and commit
    once. Committing per frame meant a 500-frame batch performed 500 fsyncs and
    drained at well under 1 frame/second; one commit per batch is what makes the
    batch worth batching.
    """
    from fmp.ingestion.cache import (
        neg_cache_key,
        resolve_company_id,
        resolve_tank_id,
        set_negative_cache,
        set_tank_cache,
    )
    from fmp.models import Tank

    sensor_serial = payload.get("sensor_serial") or payload.get("sensor_serial_number")
    raw_redis = redis.client
    tank_id = await resolve_tank_id(raw_redis, gateway_mac=gateway_mac, sensor_serial=sensor_serial)

    async with _session_scope(db_session) as session:
        tank = None
        if tank_id is not None:
            tank = await session.get(Tank, tank_id)
        if tank is None and tank_id is None:
            neg_hit = False
            if sensor_serial and await raw_redis.get(neg_cache_key(sensor_serial)) is not None:
                neg_hit = True
            if not neg_hit and gateway_mac and await raw_redis.get(neg_cache_key(gateway_mac)) is not None:
                neg_hit = True
            if neg_hit:
                return  # known-unknown device — skip DB for this frame
        tank_key = payload.get("tank_id")
        if tank is None and tank_id is None and tank_key:
            tank_id = tank_key  # legacy payload may carry tank_id directly
            tank = await session.get(Tank, tank_id)
        if tank is None and not tank_id and sensor_serial:
            tank = (
                await session.execute(
                    select(Tank).where(Tank.sensor_serial_number == sensor_serial)
                )
            ).scalar_one_or_none()
        if tank is None and gateway_mac:
            tank = (
                await session.execute(
                    select(Tank).where(Tank.gateway_mac == gateway_mac)
                )
            ).scalar_one_or_none()
        if tank is None:
            if sensor_serial:
                await set_negative_cache(raw_redis, lookup=sensor_serial)
            if gateway_mac:
                await set_negative_cache(raw_redis, lookup=gateway_mac)
            logger.warning("no tank matched for reading (gateway=%s serial=%s)",
                           gateway_mac, sensor_serial)
            return
        if tank_id is None:
            await set_tank_cache(raw_redis, tank_id=str(tank.id),
                                 gateway_mac=gateway_mac, sensor_serial=sensor_serial)

        frame = payload.get("measurement", payload)
        captured_at = frame.get("timestamp")
        if captured_at and isinstance(captured_at, str):
            try:
                captured_at = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
            except ValueError:
                captured_at = None
        if captured_at is None:
            # tz-aware: the measurements hypertable is timestamptz and a naive
            # value would be interpreted in the server's local zone (G-205).
            captured_at = datetime.now(UTC)

        company_id = await resolve_company_id(raw_redis, session, str(tank.id))
        # Liveness: every accepted frame is proof the device is talking. Without
        # this the stale sweeper would mark a perfectly healthy tank offline.
        now = datetime.now(UTC)
        tank.last_connection = now
        if tank.connection_status != "online":
            tank.connection_status = "online"

        reading = await pipeline.process(
            session,
            redis,
            tank,
            pressure=float(frame.get("pressure", 0.0)),
            temperature=float(frame.get("temperature")) if frame.get("temperature") is not None else None,
            status=int(frame.get("status", 0)),
            captured_at=captured_at,
            company_id=company_id,
        )
        if commit:
            await session.commit()
        if reading is not None:
            await publish_live(redis, reading, company_id=company_id)
        if reading is not None and reading.alarms:
            await _notify_alarms(reading, tank, company_id, captured_at)


def _record_overflow_async() -> None:
    """Persist the overflow counter without blocking the MQTT callback thread.

    Scheduling the write must never be able to fail the enqueue itself, so a
    missing event loop is tolerated rather than raised.
    """
    global _overflow_record_task
    if _overflow_record_task is not None and not _overflow_record_task.done():
        return
    try:
        _overflow_record_task = asyncio.create_task(_record_overflow())
    except RuntimeError:
        # No running loop (e.g. called from a synchronous context); the log line
        # above is still the operator's signal.
        _overflow_record_task = None


async def _record_overflow() -> None:
    try:
        redis = RedisClient()
        try:
            await _counters.record_dropped(redis.client, _dropped_reading_frames)
        finally:
            await redis.client.aclose()
    except Exception:  # noqa: BLE001 — metrics must never drop telemetry
        logger.debug("failed to record overflow counter", exc_info=True)


READ_QUEUE_MAX = 50_000
BATCH_SIZE = 500
BATCH_INTERVAL_S = 0.5

_READ_QUEUE: asyncio.Queue[tuple[dict[str, Any], str | None]] = asyncio.Queue(
    maxsize=READ_QUEUE_MAX
)
_dropped_reading_frames = 0
_overflow_record_task: asyncio.Task | None = None


def _enqueue_reading(payload: dict[str, Any], gateway_mac: str | None) -> None:
    """Accept a frame without touching the database.

    Returns immediately so a burst cannot hold an MQTT callback (and its
    connection) open; ``_flush_readings`` drains the queue over one session.
    """
    global _dropped_reading_frames
    try:
        _READ_QUEUE.put_nowait((payload, gateway_mac))
    except asyncio.QueueFull:
        _dropped_reading_frames += 1
        if _dropped_reading_frames in (1, 100, 1000) or _dropped_reading_frames % 10000 == 0:
            logger.error(
                "reading intake queue full (%d frames); dropped %d frames so far",
                READ_QUEUE_MAX,
                _dropped_reading_frames,
            )
            _record_overflow_async()


async def _flush_readings() -> None:
    """Drain queued reading frames over a single pooled connection."""
    while True:
        try:
            await asyncio.sleep(BATCH_INTERVAL_S)
        except asyncio.CancelledError:
            raise
        batch: list[tuple[dict[str, Any], str | None]] = []
        while len(batch) < BATCH_SIZE:
            try:
                batch.append(_READ_QUEUE.get_nowait())
            except asyncio.QueueEmpty:
                break
        if not batch:
            continue
        redis = RedisClient()
        started = time.perf_counter()
        persisted = 0
        try:
            async with async_session_factory() as session:
                for payload, mac in batch:
                    # A SAVEPOINT per frame: with the commit deferred to the end
                    # of the batch, a plain rollback would discard every earlier
                    # frame in the batch. The savepoint confines the damage to
                    # the one frame that failed.
                    savepoint = await session.begin_nested()
                    try:
                        await _process_reading(
                            session, redis, payload, gateway_mac=mac, commit=False
                        )
                        persisted += 1
                        await savepoint.commit()
                    except Exception:  # noqa: BLE001 — one bad frame must not drop the batch
                        logger.exception("failed to persist frame (gateway=%s)", mac)
                        await savepoint.rollback()
                # One commit for the whole batch. If it fails, nothing in the
                # batch is persisted, so the frames must be counted as unaccounted
                # rather than delivered.
                await session.commit()
            await _counters.record_received(redis.client, len(batch))
            await _counters.record_persisted(redis.client, persisted)
            await _counters.record_batch(
                redis.client,
                size=len(batch),
                latency_ms=round((time.perf_counter() - started) * 1000, 1),
                depth=_READ_QUEUE.qsize(),
            )
        except Exception:  # noqa: BLE001
            logger.exception("reading batch flush failed (%d frames)", len(batch))
            global _dropped_reading_frames
            _dropped_reading_frames += len(batch)
            try:
                # Persisted is deliberately NOT incremented: a failed commit
                # means none of this batch reached TimescaleDB.
                await _counters.record_received(redis.client, len(batch))
                await _counters.record_dropped(redis.client, len(batch))
            except Exception:  # noqa: BLE001
                logger.debug("failed to record failure metrics", exc_info=True)
        finally:
            await redis.client.aclose()


async def _notify_alarms(reading, tank, company_id: str | None, at) -> None:
    """Dispatch notifications for alarms raised by this frame (G-112).

    Runs on the ingestion path with its own session: the rule engine records the
    delivery outcome in ``notification_logs``, and a notification failure must
    never fail the reading.
    """
    from fmp.models import Site
    from fmp.services.notifications.rules import dispatch_event

    site_name = "unknown site"
    async with async_session_factory() as session:
        row = (
            await session.execute(select(Site.name).where(Site.id == tank.site_id))
        ).first()
        if row:
            site_name = row[0]
    for cand in reading.alarms:
        try:
            await dispatch_event(
                session,
                event_type="alarm",
                level=cand.level,
                company_id=uuid.UUID(company_id) if company_id else None,
                site_id=tank.site_id,
                tank_id=tank.id,
                context={
                    "tank": tank.name,
                    "site": site_name,
                    "level": cand.level,
                    "type": cand.type,
                    "value": cand.value,
                    "message": cand.message,
                    "event_ref": f"{tank.id}:{cand.type}",
                },
                default_message=(
                    "[{level}] {tank} ({site}) — {type}: {message}"
                ),
            )
        except Exception:  # noqa: BLE001 - alerting must not break ingestion
            logger.exception("alarm notification dispatch failed for tank %s", tank.id)


async def _handle_status(redis: RedisClient, payload: dict[str, Any], gateway_mac: str) -> None:
    """Update tank + owning station and (re)register the gateway on a heartbeat."""
    from fmp.models import IoTGateway, Station, Tank

    now = datetime.now(UTC)
    firmware = payload.get("firmware_version")
    async with async_session_factory() as session:
        gateway = (
            await session.execute(select(IoTGateway).where(IoTGateway.gateway_mac == gateway_mac))
        ).scalar_one_or_none()
        if gateway is None:
            gateway = IoTGateway(
                gateway_mac=gateway_mac,
                name=gateway_mac,
                firmware_version=firmware,
                connection_status="online",
                last_seen=now,
                is_active=False,
            )
            session.add(gateway)
            logger.info("gateway auto-registered: %s", gateway_mac)
        else:
            gateway.connection_status = "online"
            gateway.last_seen = now
            if firmware:
                gateway.firmware_version = firmware

        tank = (
            await session.execute(select(Tank).where(Tank.gateway_mac == gateway_mac))
        ).scalar_one_or_none()
        if tank is not None:
            tank.connection_status = "online"
            tank.last_connection = now
            if tank.site_id:
                station = (
                    await session.execute(
                        select(Station).where(Station.site_id == tank.site_id).limit(1)
                    )
                ).scalar_one_or_none()
                if station is not None:
                    station.last_heartbeat = now
        await session.commit()
        logger.info("heartbeat: gateway %s online (tank %s)", gateway_mac, tank.id if tank else None)


async def _handle_command_ack(redis: RedisClient, payload: dict[str, Any], gateway_mac: str) -> None:
    """Apply a gateway ack frame to the correlated command row."""
    from fmp.models import GatewayCommand, IoTGateway

    command_id = payload.get("command_id")
    status = payload.get("status")  # "executed" | "rejected"
    if not command_id or status not in ("executed", "rejected"):
        _dead_letter(gateway_mac, "command_ack", payload, "missing command_id or bad status")
        return
    # command_id is a UUID column: a device sending anything else used to raise
    # DataError inside the ack handler and kill the frame. Parse explicitly and
    # dead-letter instead of crashing (G-115).
    try:
        command_uuid = uuid.UUID(str(command_id))
    except (ValueError, AttributeError, TypeError):
        _dead_letter(gateway_mac, "command_ack", payload, f"command_id {command_id!r} is not a UUID")
        return
    async with async_session_factory() as session:
        row = (
            await session.execute(select(GatewayCommand).where(GatewayCommand.command_id == command_uuid))
        ).scalar_one_or_none()
        if row is None:
            logger.info("ignoring ack for unknown command_id %s", command_id)
            return
        row.status = "acked" if status == "executed" else "rejected"
        row.ack_status = status
        row.ack_detail = payload.get("detail")
        row.ack_received_at = datetime.now(UTC)
        row.next_retry_at = None
        gateway = (
            await session.execute(select(IoTGateway).where(IoTGateway.id == row.gateway_id))
        ).scalar_one_or_none()
        if gateway is not None:
            gateway.connection_status = "online"
            gateway.last_seen = datetime.now(UTC)
        await session.commit()
        logger.info("command %s %s (gateway %s)", command_id, status, gateway_mac)


@app.post("/api/v1/ingest/readings", tags=["ingest"], dependencies=[Depends(require_ingest_key)])
async def ingest_reading(frame: TelemetryFrame) -> dict:
    """Direct HTTP path (fallback for offline edge nodes).

    Requires ``X-Ingest-Key`` (see ``INGEST_API_KEY``); when no key is configured
    the endpoint is disabled (404) instead of open. The body is schema-validated,
    so an implausible frame is rejected with 422 and never reaches tank state.
    """
    redis = RedisClient()
    try:
        await _handle_reading(redis, frame.as_frame())
        return {"accepted": True, "topic": "ingestion/readings", "fields": len(frame.as_frame())}
    finally:
        await redis.client.aclose()


@app.post("/api/v1/ingest/backfill", tags=["ingest"], dependencies=[Depends(require_ingest_key)])
async def ingest_backfill(batch: BackfillBatch) -> IngestOutcome:
    """Offline buffered frames replayed by edge nodes after reconnect.

    Valid frames are applied; an invalid one is counted and reported instead of
    aborting the whole replay (a single bad buffered frame must not block a
    device's recovery after a network outage).
    """
    redis = RedisClient()
    accepted = 0
    errors: list[str] = []
    try:
        for idx, frame in enumerate(batch.frames):
            try:
                await _handle_reading(redis, frame.as_frame())
                accepted += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"frame[{idx}]: {exc}")
    finally:
        await redis.client.aclose()
    return IngestOutcome(accepted=accepted, rejected=len(batch.frames) - accepted, errors=errors)


@app.get("/api/v1/ingest/dead-letters", tags=["ingest"], dependencies=[Depends(require_ingest_key)])
async def ingest_dead_letters() -> dict:
    """Frames rejected after arrival, with the reason (operator visibility)."""
    return {"count": len(_dead_letters), "entries": dead_letters()}


@app.get("/api/v1/health", tags=["system"])
async def health() -> dict:
    connected = bool(_client and _client.is_connected())
    return {"status": "ok", "service": "ingestion", "mqtt_connected": connected}