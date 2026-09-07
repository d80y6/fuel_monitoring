"""Redis client factory and high-level caching helpers.

Responsibilities:
  - Async redis client for the API + ingestion engines
  - Code → allocation cache with TTL
  - Rate limiting (sliding window)
  - Pub/Sub for real-time telemetry fan-out
"""
from __future__ import annotations

import time
from typing import Any

import redis.asyncio as aioredis

from fmp.core.config import get_settings

settings = get_settings()


async def get_redis() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=True)


class RedisClient:
    """Thin wrapper consolidating cache + rate-limit + pub/sub operations."""

    def __init__(self, client: aioredis.Redis | None = None) -> None:
        self._client = client or aioredis.from_url(
            settings.redis_url, decode_responses=True
        )

    @property
    def client(self) -> aioredis.Redis:
        return self._client

    # ---- generic cache ----------------------------------------------------
    async def set_json(self, key: str, value: dict, ttl: int | None = None) -> None:
        import json

        payload = json.dumps(value, default=str)
        if ttl is None:
            await self._client.set(key, payload)
        else:
            await self._client.set(key, payload, ex=ttl)

    async def get_json(self, key: str) -> dict | None:
        import json

        raw = await self._client.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    async def delete(self, *keys: str) -> None:
        await self._client.delete(*keys)

    # ---- sliding-window rate limit ----------------------------------------
    async def rate_limit(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        """Returns (allowed, remaining_before_increment)."""
        now_ms = int(time.time() * 1000)
        window_start = now_ms - window_seconds * 1000
        pipe = self._client.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zcard(key)
        count, = (await pipe.execute())[-1:]
        if count >= limit:
            return False, max(0, limit - count)
        pipe = self._client.pipeline()
        pipe.zadd(key, {str(now_ms): now_ms})
        pipe.expire(key, window_seconds)
        await pipe.execute()
        return True, max(0, limit - count - 1)

    # ---- pub/sub ----------------------------------------------------------
    async def publish(self, channel: str, message: dict) -> int:
        import json

        return await self._client.publish(channel, json.dumps(message, default=str))

    async def subscribe(self, channel: str) -> aioredis.client.PubSub:
        pubsub = self._client.pubsub()
        await pubsub.subscribe(channel)
        return pubsub

    # ---- code allocation cache ---------------------------------------------
    def code_cache_key(self, code: str) -> str:
        return f"dispense:code:{code}"

    def station_validate_key(self, station_id: int) -> str:
        return f"dispense:validate:{station_id}"


async def get_redis_client() -> RedisClient:
    return RedisClient()