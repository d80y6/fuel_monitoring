"""Gateway command relay: durable Redis queue + MQTT topic helpers.

API enqueues commands (LPUSH outbound); the ingestion relay task lifts them
into an inflight list while it publishes to the broker; the sweeper requeues
unacked commands on backoff. Correlation uses a per-command UUID echoed by
the gateway on the ack topic.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fmp.core.config import get_settings

settings = get_settings()

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
