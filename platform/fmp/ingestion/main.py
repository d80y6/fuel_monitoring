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
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from fastapi import FastAPI
from paho.mqtt.client import Client as MqttClient, CallbackAPIVersion

from fmp.core.config import get_settings
from fmp.core.database import async_session_factory
from fmp.core.redis import RedisClient
from fmp.ingestion.pipeline import IngestionPipeline, publish_live
from fmp.ingestion.relay import parse_command_ack_topic
from fmp.schemas.dispensing import CodeValidateRequest, DispenseCompleteRequest
from fmp.services.dispensing.dispense_engine import complete_dispense, validate_code

logging.basicConfig(level=logging.INFO)
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
    _client = MqttClient(CallbackAPIVersion.VERSION2)
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
    yield
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


def _on_connect(client, userdata, flags, reason_code, properties):
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
                await _handle_reading(redis, payload, gateway_mac=gateway_mac)
        elif topic.startswith("ingestion/readings"):
            await _handle_reading(redis, payload)
    except Exception:  # noqa: BLE001 — a bad frame must not kill the loop
        logger.exception("failed to process frame on %s", topic)
    finally:
        await redis.client.aclose()


pipeline = IngestionPipeline(write_batch=True)


async def _handle_reading(redis: RedisClient, payload: dict[str, Any], *, gateway_mac: str | None = None) -> None:
    """Persist a tank sensor frame and fan it out to the realtime channel."""
    from fmp.ingestion.cache import resolve_tank_id, set_tank_cache, set_negative_cache, neg_cache_key
    from fmp.models import Tank

    sensor_serial = payload.get("sensor_serial") or payload.get("sensor_serial_number")
    raw_redis = redis.client
    tank_id = await resolve_tank_id(raw_redis, gateway_mac=gateway_mac, sensor_serial=sensor_serial)

    async with async_session_factory() as session:
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
            captured_at = datetime.utcnow()

        reading = await pipeline.process(
            session,
            redis,
            tank,
            pressure=float(frame.get("pressure", 0.0)),
            temperature=float(frame.get("temperature")) if frame.get("temperature") is not None else None,
            status=int(frame.get("status", 0)),
            captured_at=captured_at,
        )
        await session.commit()
        if reading is not None:
            await publish_live(redis, reading)


async def _handle_status(redis: RedisClient, payload: dict[str, Any], gateway_mac: str) -> None:
    """Update tank + owning station and (re)register the gateway on a heartbeat."""
    from fmp.models import IoTGateway, Station, Tank

    now = datetime.now(timezone.utc)
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
        logger.warning("dropped malformed ack frame from %s", gateway_mac)
        return
    async with async_session_factory() as session:
        row = (
            await session.execute(select(GatewayCommand).where(GatewayCommand.command_id == command_id))
        ).scalar_one_or_none()
        if row is None:
            logger.info("ignoring ack for unknown command_id %s", command_id)
            return
        row.status = "acked" if status == "executed" else "rejected"
        row.ack_status = status
        row.ack_detail = payload.get("detail")
        row.ack_received_at = datetime.now(timezone.utc)
        row.next_retry_at = None
        gateway = (
            await session.execute(select(IoTGateway).where(IoTGateway.id == row.gateway_id))
        ).scalar_one_or_none()
        if gateway is not None:
            gateway.connection_status = "online"
            gateway.last_seen = datetime.now(timezone.utc)
        await session.commit()
        logger.info("command %s %s (gateway %s)", command_id, status, gateway_mac)


@app.post("/api/v1/ingest/readings", tags=["ingest"])
async def ingest_reading(frame: dict) -> dict:
    """Direct HTTP path (fallback for offline edge nodes)."""
    redis = RedisClient()
    try:
        await _handle_reading(redis, frame)
        return {"accepted": True, "topic": "ingestion/readings", "fields": len(frame)}
    finally:
        await redis.client.aclose()


@app.post("/api/v1/ingest/backfill", tags=["ingest"])
async def ingest_backfill(frames: list[dict]) -> dict:
    """Offline buffered frames replayed by edge nodes after reconnect."""
    redis = RedisClient()
    accepted = 0
    try:
        for frame in frames:
            await _handle_reading(redis, frame)
            accepted += 1
    finally:
        await redis.client.aclose()
    return {"accepted": accepted}


@app.get("/api/v1/health", tags=["system"])
async def health() -> dict:
    connected = bool(_client and _client.is_connected())
    return {"status": "ok", "service": "ingestion", "mqtt_connected": connected}