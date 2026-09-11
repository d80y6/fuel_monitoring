"""Unit tests: gateway command relay queue + MQTT contract helpers."""
from __future__ import annotations

import pytest

from fmp.ingestion.relay import (
    QUEUE_INFLIGHT,
    QUEUE_OUTBOUND,
    ack_topic_for,
    command_relay_loop,
    command_topic_for,
    compute_backoff,
    enqueue_command,
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


@pytest.mark.asyncio
async def test_relay_loop_publishes_and_marks_sent():
    redis = FakeRedis()
    marked = []

    class FakeClient:
        def __init__(self):
            self.topics = []

        def publish(self, topic, payload, qos=1):
            self.topics.append(topic)
            return (0, 1)  # MQTT_ERR_SUCCESS

    client = FakeClient()
    await enqueue_command(
        redis, command_id="cmd-1", gateway_mac="AA:BB:CC:DD:EE:01",
        command_type="reboot", payload={},
    )
    await command_relay_loop(
        client, redis=redis, mark_sent=marked.append, max_frames=1
    )
    assert marked == ["cmd-1"]
    assert client.topics == ["fuel/AA:BB:CC:DD:EE:01/command"]
    assert await redis.llen(QUEUE_OUTBOUND) == 0
    assert await redis.llen(QUEUE_INFLIGHT) == 0


@pytest.mark.asyncio
async def test_relay_loop_keeps_inflight_on_publish_reject():
    redis = FakeRedis()

    class RejectClient:
        def publish(self, topic, payload, qos=1):
            return (1, 0)  # rc != MQTT_ERR_SUCCESS

    await enqueue_command(
        redis, command_id="cmd-2", gateway_mac="AA:BB:CC:DD:EE:02",
        command_type="reboot", payload={},
    )
    await command_relay_loop(
        RejectClient(), redis=redis, mark_sent=lambda cid: None, max_frames=1
    )
    assert await redis.llen(QUEUE_OUTBOUND) == 0
    assert await redis.llen(QUEUE_INFLIGHT) == 1


@pytest.mark.asyncio
async def test_relay_loop_requeues_on_mark_sent_failure():
    redis = FakeRedis()
    calls = {"n": 0}

    class OkClient:
        def publish(self, topic, payload, qos=1):
            return (0, 1)

    async def boom(_cid):
        calls["n"] += 1
        raise RuntimeError("db down")

    await enqueue_command(
        redis, command_id="cmd-3", gateway_mac="AA:BB:CC:DD:EE:03",
        command_type="reboot", payload={},
    )
    await command_relay_loop(OkClient(), redis=redis, mark_sent=boom, max_frames=1)
    assert calls["n"] >= 1
    # frame was re-queued to outbound after mark_sent failure
    assert await redis.llen(QUEUE_OUTBOUND) == 1
    assert await redis.llen(QUEUE_INFLIGHT) == 0
