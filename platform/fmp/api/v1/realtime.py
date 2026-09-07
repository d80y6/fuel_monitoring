"""Realtime telemetry endpoints (WebSocket streaming over Redis pub/sub)."""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from fmp.api.realtime import manager
from fmp.core.redis import RedisClient, get_redis_client
from fmp.core.security import get_current_user_from_query

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/telemetry")
async def ws_telemetry(
    ws: WebSocket,
    channels: list[str] = Query(default=["telemetry"]),
    token: str = Query(...),
    redis: RedisClient = Depends(get_redis_client),
):
    """Stream live telemetry + alarms.

    Authorization mirrors the REST API: the client passes a JWT as ``?token=``;
    the allowed scope is the broadcast channel (or a comma-separated per-tank
    list via ``channels``).
    """
    user = await get_current_user_from_query(token)
    if user is None:
        await ws.close(code=4401)
        return

    await ws.accept()
    allowed = tuple(c for c in channels if c)
    await manager.subscribe(ws, allowed)
    logger.info("ws subscriber connected: user=%s channels=%s", user.get("sub"), allowed)

    pubsub = redis.client.pubsub()
    await pubsub.subscribe("telemetry:live", "alarms:live")
    try:
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.2)
            if msg and msg.get("type") == "message":
                payload = json.loads(msg["data"])
                channel = "telemetry" if msg["channel"] == "telemetry:live" else "alarms"
                if not allowed or any(channel.startswith(c) for c in allowed):
                    await ws.send_json(payload)
    except WebSocketDisconnect:
        pass
    finally:
        await manager.unsubscribe(ws)
        await pubsub.unsubscribe()
        await pubsub.close()


@router.websocket("/ws/alarms")
async def ws_alarms(
    ws: WebSocket,
    token: str = Query(...),
    redis: RedisClient = Depends(get_redis_client),
):
    user = await get_current_user_from_query(token)
    if user is None:
        await ws.close(code=4401)
        return
    await ws.accept()
    await manager.subscribe(ws, ("alarms",))
    pubsub = redis.client.pubsub()
    await pubsub.subscribe("alarms:live")
    try:
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.2)
            if msg and msg.get("type") == "message":
                await ws.send_json(json.loads(msg["data"]))
    except WebSocketDisconnect:
        pass
    finally:
        await manager.unsubscribe(ws)
        await pubsub.unsubscribe()
        await pubsub.close()


@router.get("/api/v1/realtime/metrics", tags=["realtime"])
async def realtime_metrics() -> dict:
    return {"subscribers": manager.subscriber_count}