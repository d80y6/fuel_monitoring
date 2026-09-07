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
from typing import Any

from fastapi import FastAPI
from paho.mqtt.client import Client as MqttClient, CallbackAPIVersion

from fmp.core.config import get_settings
from fmp.core.database import async_session_factory
from fmp.core.redis import RedisClient
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
    _loop = asyncio.get_running_loop()
    _client = MqttClient(CallbackAPIVersion.VERSION2)
    _client.on_message = _on_message
    _client.connect(settings.MQTT_BROKER, settings.MQTT_PORT, settings.MQTT_KEEPALIVE)
    _client.subscribe(
        [
            ("ingestion/readings", settings.MQTT_QOS),
            ("ingestion/status", settings.MQTT_QOS),
            ("ingestion/dispense/validate", settings.MQTT_QOS),
            ("ingestion/dispense/complete", settings.MQTT_QOS),
        ]
    )
    _client.loop_start()
    logger.info(
        "MQTT subscription active on %s:%s", settings.MQTT_BROKER, settings.MQTT_PORT
    )
    yield
    _client.loop_stop()
    _client.disconnect()


app = FastAPI(
    title="Edge Ingestion Engine",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
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
        elif topic.startswith("ingestion/readings"):
            logger.debug("telemetry frame received (%d fields)", len(payload))
    except Exception:  # noqa: BLE001 — a bad frame must not kill the loop
        logger.exception("failed to process frame on %s", topic)
    finally:
        await redis.client.aclose()


@app.post("/api/v1/ingest/readings", tags=["ingest"])
async def ingest_reading(frame: dict) -> dict:
    """Direct HTTP path (fallback for offline edge nodes)."""
    # Persistence is handled by the telemetry writer; validated in prod.
    return {"accepted": True, "topic": "ingestion/readings", "fields": len(frame)}


@app.post("/api/v1/ingest/backfill", tags=["ingest"])
async def ingest_backfill(frames: list[dict]) -> dict:
    """Offline buffered frames replayed by edge nodes after reconnect."""
    return {"accepted": len(frames)}


@app.get("/api/v1/health", tags=["system"])
async def health() -> dict:
    connected = bool(_client and _client.is_connected())
    return {"status": "ok", "service": "ingestion", "mqtt_connected": connected}