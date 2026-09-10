"""Unit tests: tank TTL cache + fuel-topic key helpers."""
from __future__ import annotations

import pytest

from fmp.ingestion.cache import (
    TANK_CACHE_TTL,
    TANK_NEG_TTL,
    neg_cache_key,
    resolve_tank_id,
    serial_cache_key,
    gateway_cache_key,
)
from fmp.tests.conftest import FakeRedis


@pytest.mark.asyncio
async def test_key_helpers():
    assert serial_cache_key("SN-1") == "tank:by:serial:SN-1"
    assert gateway_cache_key("AA:BB") == "tank:by:gateway:AA:BB"
    assert neg_cache_key("SN-1") == "tank:neg:SN-1"


@pytest.mark.asyncio
async def test_cache_ttl_constants():
    assert TANK_CACHE_TTL == 300
    assert TANK_NEG_TTL == 60


@pytest.mark.asyncio
async def test_serial_hit_returns_tank_id():
    redis = FakeRedis(store={"tank:by:serial:SN-1": '"11111111-1111-1111-1111-111111111111"'})
    assert await resolve_tank_id(redis, sensor_serial="SN-1") == \
        "11111111-1111-1111-1111-111111111111"


@pytest.mark.asyncio
async def test_negative_cache_returns_none():
    redis = FakeRedis(store={
        "tank:by:serial:SN-1": '"11111111-1111-1111-1111-111111111111"',
        "tank:neg:SN-1": '"__NULL__"',
    })
    assert await resolve_tank_id(redis, sensor_serial="SN-1") is None


@pytest.mark.asyncio
async def test_gateway_miss_returns_none():
    redis = FakeRedis()
    assert await resolve_tank_id(redis, gateway_mac="AA:BB") is None
