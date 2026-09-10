"""Tank resolution cache (MQTT topic/gateway → tank).

Speeds up `fuel/{gateway_mac}/readings` and legacy `ingestion/readings`
frames by caching tank_id behind gateway_mac / sensor_serial. DB lookups only
happen on cache miss; unknown devices get a short negative-cache entry so they
don't hot-loop the database.
"""
from __future__ import annotations

import json

TANK_CACHE_TTL = 300  # seconds
TANK_NEG_TTL = 60     # seconds
_NULL = "__NULL__"


def serial_cache_key(serial: str) -> str:
    return f"tank:by:serial:{serial}"


def gateway_cache_key(mac: str) -> str:
    return f"tank:by:gateway:{mac}"


def neg_cache_key(lookup: str) -> str:
    return f"tank:neg:{lookup}"


async def resolve_tank_id(redis, *, gateway_mac: str | None = None,
                          sensor_serial: str | None = None) -> str | None:
    """Return a cached tank_id or None.

    Only reads the cache — the caller performs the DB upsert on miss.
    Precedence: gateway_mac first, then sensor_serial.
    """
    if gateway_mac:
        lookup = gateway_mac
        key = gateway_cache_key(lookup)
    elif sensor_serial:
        lookup = sensor_serial
        key = serial_cache_key(lookup)
    else:
        return None

    if await redis.get(neg_cache_key(lookup)) is not None:
        return None  # negative entry: resume after TANK_NEG_TTL

    raw = await redis.get(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None


async def set_tank_cache(redis, *, tank_id: str,
                         gateway_mac: str | None = None,
                         sensor_serial: str | None = None) -> None:
    if gateway_mac:
        await redis.set(gateway_cache_key(gateway_mac), json.dumps(tank_id), ex=TANK_CACHE_TTL)
    if sensor_serial:
        await redis.set(serial_cache_key(sensor_serial), json.dumps(tank_id), ex=TANK_CACHE_TTL)


async def set_negative_cache(redis, *, lookup: str) -> None:
    await redis.set(neg_cache_key(lookup), json.dumps(_NULL), ex=TANK_NEG_TTL)
