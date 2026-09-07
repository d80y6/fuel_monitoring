"""Realtime push manager: broadcasts telemetry/alarms to authenticated WebSocket clients.

A lightweight in-process pub/sub bridge: the ingestion pipeline fan-outs to a
live channel; every connected, authorised client receives the frames it is
allowed to see (channel-filtered by an access-control key).
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class RealtimeManager:
    """Tracks active WebSocket subscribers and their allowed channel prefixes."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._subscriptions: dict[WebSocket, tuple[str, ...]] = {}

    async def subscribe(self, ws: WebSocket, channels: tuple[str, ...]) -> None:
        async with self._lock:
            self._subscriptions[ws] = channels

    async def unsubscribe(self, ws: WebSocket) -> None:
        async with self._lock:
            self._subscriptions.pop(ws, None)

    async def broadcast(self, channel: str, message: dict) -> int:
        """Deliver ``message`` to subscribers whose allowed channels match.

        A subscriber with an empty channel tuple receives everything (broadcast
        role). Returns the number of clients the message was sent to.
        """
        from fastapi import WebSocketDisconnect

        stale: list[WebSocket] = []
        sent = 0
        async with self._lock:
            recipients = list(self._subscriptions.items())
        for ws, channels in recipients:
            if channels and not any(channel.startswith(c) for c in channels):
                continue
            try:
                await ws.send_json(message)
                sent += 1
            except (WebSocketDisconnect, RuntimeError):
                stale.append(ws)
        for ws in stale:
            await self.unsubscribe(ws)
        return sent

    @property
    def subscriber_count(self) -> int:
        return len(self._subscriptions)


manager = RealtimeManager()