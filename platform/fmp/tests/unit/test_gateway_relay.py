"""Unit tests: gateway command relay queue + MQTT contract helpers."""
from __future__ import annotations

import pytest

from fmp.ingestion.relay import (
    QUEUE_INFLIGHT,
    QUEUE_OUTBOUND,
    ack_topic_for,
    command_topic_for,
    compute_backoff,
    parse_command_ack_topic,
)
from fmp.tests.conftest import FakeRedis


@pytest.mark.asyncio
async def test_queue_key_constants():
    assert QUEUE_OUTBOUND == "iot:commands:outbound"
    assert QUEUE_INFLIGHT == "iot:commands:inflight"


@pytest.mark.asyncio
async def test_topic_builders():
    assert command_topic_for("AA:BB:CC:DD:EE:01") == "fuel/AA:BB:CC:DD:EE:01/command"
    assert ack_topic_for("AA:BB:CC:DD:EE:01") == "fuel/AA:BB:CC:DD:EE:01/command/ack"


@pytest.mark.asyncio
async def test_ack_topic_parse():
    assert parse_command_ack_topic("fuel/AA:BB:CC:DD:EE:01/command/ack") == "AA:BB:CC:DD:EE:01"
    assert parse_command_ack_topic("fuel/AA:BB/readings") is None


@pytest.mark.asyncio
async def test_backoff_exponential_capped():
    assert compute_backoff(1) == 60
    assert compute_backoff(2) == 120
    # cap at 900 despite large exponent
    assert compute_backoff(10) == 900


@pytest.mark.asyncio
async def test_relay_roundtrip_via_fake_redis():
    redis = FakeRedis()
    await redis.lpush(QUEUE_OUTBOUND, "msg-1")
    item = await redis.brpoplpush(QUEUE_OUTBOUND, QUEUE_INFLIGHT, timeout=1)
    assert item == "msg-1"
    assert await redis.llen(QUEUE_INFLIGHT) == 1
    assert await redis.lpop(QUEUE_INFLIGHT) == "msg-1"
