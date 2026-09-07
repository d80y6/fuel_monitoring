"""Test fixtures for the platform test-suite.

Infrastructure-backed tests (dispense engine, totalizer audit, full flow)
connect to PostgreSQL/TimescaleDB and Redis described via environment
variables. If the hosts are unreachable the tests are skipped so the unit
layer stays runnable anywhere.
"""
from __future__ import annotations

import os
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import pytest
import pytest_asyncio

# Run every test with a connection-per-use DB pool (see fmp/core/database.py):
# pytest-asyncio gives each test its own event loop, so a shared pool leaks
# asyncpg connections across loops.
os.environ.setdefault("FMP_TESTING", "1")


# --------------------------------------------------------------------------
# Minimal in-memory Redis stand-in (hermetic unit tests)
# --------------------------------------------------------------------------
@dataclass
class FakeRedis:
    store: dict = field(default_factory=dict)
    sets: dict = field(default_factory=dict)
    zsets: dict = field(default_factory=dict)
    published: list = field(default_factory=list)

    @property
    def client(self):
        return self

    async def sismember(self, key: str, member: str) -> bool:
        return member in self.sets.get(key, set())

    async def sadd(self, key: str, member: str) -> int:
        self.sets.setdefault(key, set()).add(member)
        return 1

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value, ex=None, nx=False):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def delete(self, *keys):
        n = 0
        for k in keys:
            n += int(self.store.pop(k, None) is not None)
        return n

    async def zadd(self, key: str, mapping: dict):
        self.zsets.setdefault(key, {})
        for member, score in mapping.items():
            self.zsets[key][member] = score
        return len(mapping)

    async def zremrangebyscore(self, key, *_):
        return 0

    async def zcard(self, key: str) -> int:
        return len(self.zsets.get(key, {}))

    async def expire(self, key, seconds):
        return True

    async def publish(self, channel, message):
        import json

        # real RedisClient encodes dicts to JSON strings internally
        if not isinstance(message, str):
            message = json.dumps(message, default=str)
        self.published.append((channel, message))
        return 1

    async def aclose(self):
        return None

    # --- RedisClient helper parity (used by the dispense engine) -----------
    async def set_json(self, key: str, value: dict, ttl: int | None = None):
        import json

        self.store[key] = json.dumps(value, default=str)

    async def get_json(self, key: str):
        import json

        raw = self.store.get(key)
        return json.loads(raw) if raw is not None else None

    async def rate_limit(self, key: str, limit: int, window_seconds: int):
        return True, limit


@pytest_asyncio.fixture
async def fake_redis() -> AsyncIterator[FakeRedis]:
    yield FakeRedis()


@pytest_asyncio.fixture(autouse=True)
async def _dispose_engine_between_tests():
    """Drop any pooled/held asyncpg connections so they never leak across tests.

    pytest-asyncio gives each test its own event loop; a connection opened on a
    prior loop breaks when reused. Disposing the shared engine after each test
    forces the next connection to be created on the current loop.
    """
    yield
    try:
        from fmp.core.database import engine

        await engine.dispose()
    except Exception:
        pass


# --------------------------------------------------------------------------
# Real infrastructure (optional)
# --------------------------------------------------------------------------
def _infra_available() -> bool:
    return os.environ.get("FMP_TEST_INFRA", "1") == "1" or True


@pytest.fixture
def requires_infra():
    """Skip whole test modules that need a live DB/Redis unless enabled."""
    if os.getenv("FMP_SKIP_INFRA") == "1":
        pytest.skip("FMP_SKIP_INFRA=1 set")

    # Lazily probe the configured Postgres port.
    import socket

    host = os.getenv("POSTGRES_HOST", "localhost")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    try:
        with socket.create_connection((host, port), timeout=1.5):
            return True
    except OSError:
        pytest.skip(f"Postgres not reachable at {host}:{port}")