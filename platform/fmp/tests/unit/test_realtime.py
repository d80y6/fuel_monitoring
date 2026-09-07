"""Unit tests for the realtime manager broadcast/filter logic + query-token auth."""
from __future__ import annotations

import pytest

from fmp.api.realtime import RealtimeManager
from fmp.core.security import create_access_token, get_current_user_from_query


class StubWS:
    def __init__(self, uid: int) -> None:
        self.uid = uid
        self.sent: list[dict] = []
        self.fail_on_send = False

    async def send_json(self, message: dict) -> None:
        if self.fail_on_send:
            raise RuntimeError("socket closed")
        self.sent.append(message)


@pytest.mark.asyncio
async def test_broadcast_delivers_to_matching_channel():
    mgr = RealtimeManager()
    ws = StubWS(1)
    await mgr.subscribe(ws, ("telemetry",))
    n = await mgr.broadcast("telemetry", {"level": 2.0})
    assert n == 1
    assert ws.sent == [{"level": 2.0}]


@pytest.mark.asyncio
async def test_broadcast_filters_non_matching_channel():
    mgr = RealtimeManager()
    ws = StubWS(1)
    await mgr.subscribe(ws, ("telemetry",))
    n = await mgr.broadcast("alarms", {"type": "x"})
    assert n == 0
    assert ws.sent == []


@pytest.mark.asyncio
async def test_catch_all_subscriber_receives_everything():
    mgr = RealtimeManager()
    ws = StubWS(1)
    await mgr.subscribe(ws, ())
    assert await mgr.broadcast("telemetry", {}) == 1
    assert await mgr.broadcast("alarms", {}) == 1


@pytest.mark.asyncio
async def test_broadcast_drops_stale_websockets():
    mgr = RealtimeManager()
    good, bad = StubWS(1), StubWS(2)
    bad.fail_on_send = True
    await mgr.subscribe(good, ())
    await mgr.subscribe(bad, ())
    n = await mgr.broadcast("telemetry", {})
    assert n == 1
    assert mgr.subscriber_count == 1


def test_query_token_auth_accepts_valid_token():
    token = create_access_token(subject=42)
    claims = get_current_user_from_query(token)
    assert claims is not None
    assert claims["sub"] == "42"


def test_query_token_auth_rejects_garbage():
    assert get_current_user_from_query("not-a-jwt") is None