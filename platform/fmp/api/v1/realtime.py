"""Realtime telemetry + alarm streaming (WebSocket over Redis pub/sub).

Tenant isolation is enforced **here**, on the streaming path (G-003). Every
event published by the ingestion pipeline carries ``company_id``; a socket only
ever forwards the events whose company matches the authenticated caller's
tenant. Platform operators (``role == "admin"`` with no company) receive
everything.

The connection's identity is resolved from the database on handshake rather than
read from token claims, so a token minted before a role/tenant change cannot
widen the stream. Revoked tokens are rejected with 4401.
"""
from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from fmp.api.deps import CurrentUser
from fmp.api.realtime import manager
from fmp.core.database import async_session_factory
from fmp.core.redis import RedisClient, get_redis_client
from fmp.core.security import get_current_user_from_query, token_revoked
from fmp.models import User

logger = logging.getLogger(__name__)

router = APIRouter()


async def _resolve_ws_user(token: str, redis: RedisClient) -> User | None:
    """DB-authoritative identity for a socket handshake, or None if invalid."""
    claims = get_current_user_from_query(token)
    if claims is None:
        return None
    if await token_revoked(redis, claims):
        return None
    try:
        user_id = uuid.UUID(str(claims.get("sub")))
    except (ValueError, TypeError):
        return None
    async with async_session_factory() as session:
        user = (
            await session.execute(
                select(User).where(User.id == user_id, User.is_active.is_(True),
                                   User.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
        if user is None:
            return None
        # Detach from the closing session so the socket can hold it safely.
        session.expunge(user)
        return user


def _is_platform(user: User) -> bool:
    return user.role == "admin" and user.company_id is None


def _event_visible(payload: dict, user: User) -> bool:
    """A socket receives an event only if it belongs to the caller's tenant."""
    if _is_platform(user):
        return True
    event_company = payload.get("company_id")
    if event_company is None:
        # Events from before the tenant field existed, or from a tank whose site
        # is gone: refuse rather than leak across tenants.
        return False
    return str(event_company) == str(user.company_id)


async def _stream(ws: WebSocket, redis: RedisClient, user: User, channels: set[str]) -> None:
    pubsub = redis.client.pubsub()
    await pubsub.subscribe("telemetry:live", "alarms:live")
    try:
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.2)
            if not msg or msg.get("type") != "message":
                continue
            channel = "telemetry" if msg["channel"] == "telemetry:live" else "alarms"
            if channels and channel not in channels:
                continue
            try:
                payload = json.loads(msg["data"])
            except (TypeError, ValueError):
                logger.warning("dropping unparseable %s event", channel)
                continue
            if not isinstance(payload, dict) or not _event_visible(payload, user):
                continue
            await ws.send_json(payload)
    except WebSocketDisconnect:
        pass
    finally:
        await manager.unsubscribe(ws)
        await pubsub.unsubscribe()
        await pubsub.close()


@router.websocket("/ws/telemetry")
async def ws_telemetry(
    ws: WebSocket,
    channels: list[str] = Query(default=["telemetry"]),
    token: str = Query(...),
    redis: RedisClient = Depends(get_redis_client),
):
    """Stream live telemetry and/or alarms for the caller's tenant."""
    user = await _resolve_ws_user(token, redis)
    if user is None:
        await ws.close(code=4401)
        return

    await ws.accept()
    requested = {c for c in channels if c in ("telemetry", "alarms")}
    if not requested:
        requested = {"telemetry"}
    await manager.subscribe(ws, tuple(requested))
    logger.info("ws telemetry connected: user=%s company=%s channels=%s",
                user.username, user.company_id, sorted(requested))
    await _stream(ws, redis, user, requested)


@router.websocket("/ws/alarms")
async def ws_alarms(
    ws: WebSocket,
    token: str = Query(...),
    redis: RedisClient = Depends(get_redis_client),
):
    """Alarm stream only, for the caller's tenant."""
    user = await _resolve_ws_user(token, redis)
    if user is None:
        await ws.close(code=4401)
        return
    await ws.accept()
    await manager.subscribe(ws, ("alarms",))
    logger.info("ws alarms connected: user=%s company=%s", user.username, user.company_id)
    await _stream(ws, redis, user, {"alarms"})


@router.get("/api/v1/realtime/metrics", tags=["realtime"])
async def realtime_metrics(_current: CurrentUser) -> dict:
    """Connection count. Authenticated — previously exposed to anonymous callers."""
    return {"subscribers": manager.subscriber_count}
