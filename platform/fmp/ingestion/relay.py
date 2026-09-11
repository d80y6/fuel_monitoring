"""Gateway command relay: durable Redis queue + MQTT topic helpers.

API enqueues commands (LPUSH outbound); the ingestion relay task lifts them
into an inflight list while it publishes to the broker; the sweeper requeues
unacked commands on backoff. Correlation uses a per-command UUID echoed by
the gateway on the ack topic.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
from datetime import datetime, timedelta, timezone

from fmp.core.config import get_settings

settings = get_settings()
logger = logging.getLogger("ingestion.relay")

QUEUE_OUTBOUND = settings.COMMAND_QUEUE_OUTBOUND
QUEUE_INFLIGHT = settings.COMMAND_QUEUE_INFLIGHT


def command_topic_for(gateway_mac: str) -> str:
    return f"fuel/{gateway_mac}/command"


def ack_topic_for(gateway_mac: str) -> str:
    return f"fuel/{gateway_mac}/command/ack"


def parse_command_ack_topic(topic: str) -> str | None:
    """``fuel/<mac>/command/ack`` → mac (or None)."""
    parts = topic.split("/")
    if len(parts) == 4 and parts[0] == "fuel" and parts[2] == "command" and parts[3] == "ack":
        return parts[1]
    return None


def compute_backoff(attempts: int) -> int:
    """Exponential backoff in seconds: base * 2^(attempts-1), capped."""
    seconds = settings.COMMAND_BACKOFF_BASE_SECONDS * (2 ** (attempts - 1))
    return min(seconds, settings.COMMAND_BACKOFF_MAX_SECONDS)


def next_retry_datetime(attempts: int) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=compute_backoff(attempts))


async def enqueue_command(redis, *, command_id: str, gateway_mac: str,
                          command_type: str, payload: dict,
                          issued_at: str | None = None) -> int:
    """LPUSH one command frame onto the durable outbound queue."""
    message = {
        "command_id": command_id,
        "gateway_mac": gateway_mac,
        "type": command_type,
        "payload": payload,
        "issued_at": issued_at or datetime.now(timezone.utc).isoformat(),
    }
    return await redis.lpush(QUEUE_OUTBOUND, json.dumps(message, default=str))


async def drain_inflight(redis) -> None:
    """Return any leftover inflight frames to outbound on startup."""
    while True:
        item = await redis.rpoplpush(QUEUE_INFLIGHT, QUEUE_OUTBOUND)
        if item is None:
            return


async def take_command(redis, timeout: int = 1) -> dict | None:
    """Blocking BLPOP outbound → inflight handoff; returns parsed frame or None."""
    raw = await redis.brpoplpush(QUEUE_OUTBOUND, QUEUE_INFLIGHT, timeout=timeout)
    if raw is None:
        return None
    return json.loads(raw)


async def release_command(redis) -> None:
    """Pop the currently-holding inflight frame after successful publish."""
    await redis.lpop(QUEUE_INFLIGHT)


async def publish_command(_client, redis, command_id: str, gateway_mac: str,
                          command_type: str, payload: dict, attempts: int) -> bool:
    """Publish one command frame to MQTT. Returns True on accepted publish."""
    from paho.mqtt.client import MQTT_ERR_SUCCESS

    frame = {
        "command_id": command_id,
        "type": command_type,
        "payload": payload,
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "attempts": attempts,
    }
    rc, _mid = _client.publish(
        command_topic_for(gateway_mac), json.dumps(frame, default=str),
        qos=settings.MQTT_QOS,
    )
    return rc == MQTT_ERR_SUCCESS


async def command_relay_loop(_client, *, redis=None, mark_sent=None, max_frames=None) -> None:
    """Continuously move outbound frames to MQTT while they exist.

    ``max_frames`` bounds how many outbound frames are processed before the
    loop returns (mainly for deterministic tests); ``None`` runs forever.
    """
    from fmp.core.redis import RedisClient

    owns_redis = redis is None
    if owns_redis:
        redis_cache = RedisClient()
        redis = redis_cache.client
    do_mark = mark_sent or _mark_sent
    taken = 0
    try:
        await drain_inflight(redis)
        while True:
            try:
                frame = await take_command(redis, timeout=1)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — transient Redis errors must not kill the relay
                logger.exception("relay take_command failed; backing off 1s")
                await asyncio.sleep(1)
                continue
            if frame is None:
                await asyncio.sleep(0)  # yield so cancellation is deliverable
                continue
            taken += 1
            try:
                ok = await publish_command(
                    _client, redis,
                    command_id=frame["command_id"],
                    gateway_mac=frame["gateway_mac"],
                    command_type=frame["type"],
                    payload=frame.get("payload", {}),
                    attempts=int(frame.get("attempts", 0)) + 1,
                )
                if ok:
                    await release_command(redis)
                    result = do_mark(frame["command_id"])
                    if inspect.isawaitable(result):
                        await result
                else:
                    # frame stays in inflight; sweeper will requeue
                    logger.warning("MQTT publish rejected for %s", frame["command_id"])
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — failure after publish must not lose the frame
                logger.exception("relay failed for %s; re-queuing frame", frame["command_id"])
                await redis.lpush(QUEUE_OUTBOUND, json.dumps(frame, default=str))
            if max_frames is not None and taken >= max_frames:
                return
    finally:
        if owns_redis:
            await redis_cache.client.aclose()


async def _mark_sent(command_id: str) -> None:
    from sqlalchemy import select

    from fmp.core.database import async_session_factory
    from fmp.models import GatewayCommand

    async with async_session_factory() as session:
        row = (
            await session.execute(select(GatewayCommand).where(GatewayCommand.command_id == command_id))
        ).scalar_one_or_none()
        if row is None:
            return
        row.status = "sent"
        row.sent_at = datetime.now(timezone.utc)
        row.attempts += 1
        row.next_retry_at = next_retry_datetime(row.attempts)
        await session.commit()
