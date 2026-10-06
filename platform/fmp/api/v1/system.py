"""Health, readiness and platform metrics (audit G-201).

Three distinct questions, deliberately separated because they mean different
things to an operator and to an orchestrator:

``/api/v1/health``  liveness — is this process running? Never touches a
    dependency, so a database outage cannot cause the orchestrator to kill a
    perfectly healthy API.
``/api/v1/readyz``  readiness — can this process actually serve traffic? Checks
    the database, Redis and the MQTT broker, and reports each independently so
    the failure is identifiable rather than a single opaque ``503``.
``/api/v1/metrics``  operational counters — whether telemetry is arriving, how
    stale it is, how many alarms are open, whether delivery is succeeding.

The metrics endpoint answers the questions that decide whether a fuel-monitoring
platform is trustworthy: is data flowing, is it fresh, are alarms being
evaluated, are notifications being delivered, are devices talking.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Response
from sqlalchemy import text

from fmp.api.deps import AdminUser
from fmp.core.config import get_settings

settings = get_settings()
router = APIRouter(tags=["system"])


@router.get("/api/v1/health")
async def health() -> dict:
    """Liveness. Intentionally dependency-free so a backend outage never restarts us."""
    return {"status": "ok", "service": "api", "time": datetime.now(UTC).isoformat()}


async def _check_database() -> dict:
    try:
        from fmp.core.database import engine

        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001 - the failure detail is the payload
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


async def _check_redis() -> dict:
    try:
        from fmp.core.redis import RedisClient

        client = RedisClient()
        try:
            pong = await client.client.ping()
            return {"ok": bool(pong)}
        finally:
            await client.client.aclose()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


async def _check_mqtt() -> dict:
    """Broker reachability.

    Probed by opening a short-lived TCP connection to the configured broker. The
    API process is not an MQTT client (ingestion is), so this answers "is the
    broker reachable from this network" rather than "is this process subscribed".
    """
    import socket

    try:
        with socket.create_connection((settings.MQTT_BROKER, settings.MQTT_PORT), timeout=3):
            return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@router.get("/api/v1/readyz")
async def readyz(response: Response) -> dict:
    """Readiness. 503 when any dependency is down, with the reason per dependency."""
    checks = {
        "database": await _check_database(),
        "redis": await _check_redis(),
        "mqtt": await _check_mqtt(),
    }
    failed = [name for name, result in checks.items() if not result.get("ok")]
    ready = not failed
    if not ready:
        response.status_code = 503
    return {
        "status": "ready" if ready else "not_ready",
        "failed": failed,
        "checks": checks,
        "time": datetime.now(UTC).isoformat(),
    }


@router.get("/api/v1/metrics")
async def metrics(_current: AdminUser) -> dict:
    """Operational counters. Admin-only: it exposes fleet topology.

    These are the questions an operator actually asks when told "the fuel
    numbers look wrong": is telemetry arriving, how fresh is it, are devices
    talking, are alarms open, is notification delivery succeeding.
    """
    from sqlalchemy import func, select

    from fmp.core.database import async_session_factory
    from fmp.models import Alarm, IoTGateway, Tank

    now = datetime.now(UTC)
    cutoff = now - timedelta(seconds=settings.TANK_STALE_AFTER_SECONDS)
    day_ago = now - timedelta(days=1)

    async with async_session_factory() as session:
        total_tanks = (
            await session.execute(
                select(func.count()).select_from(Tank).where(Tank.deleted_at.is_(None))
            )
        ).scalar_one()
        offline_tanks = (
            await session.execute(
                select(func.count()).select_from(Tank).where(
                    Tank.deleted_at.is_(None), Tank.connection_status == "offline"
                )
            )
        ).scalar_one()
        stale_tanks = (
            await session.execute(
                select(func.count()).select_from(Tank).where(
                    Tank.deleted_at.is_(None),
                    Tank.last_connection.is_not(None),
                    Tank.last_connection < cutoff,
                )
            )
        ).scalar_one()
        never_seen = (
            await session.execute(
                select(func.count()).select_from(Tank).where(
                    Tank.deleted_at.is_(None), Tank.last_connection.is_(None)
                )
            )
        ).scalar_one()

        open_alarms = (
            await session.execute(
                select(func.count()).select_from(Alarm).where(
                    Alarm.state.in_(("active", "acknowledged", "escalated"))
                )
            )
        ).scalar_one()
        resolved_alarms = (
            await session.execute(
                select(func.count()).select_from(Alarm).where(Alarm.state == "resolved")
            )
        ).scalar_one()

        newest_reading = (
            await session.execute(text("SELECT MAX(timestamp) FROM measurements"))
        ).scalar_one()

        gateway_total = (
            await session.execute(select(func.count()).select_from(IoTGateway))
        ).scalar_one()
        gateway_online = (
            await session.execute(
                select(func.count()).select_from(IoTGateway).where(
                    IoTGateway.connection_status == "online"
                )
            )
        ).scalar_one()

        delivery = (
            await session.execute(
                text(
                    "SELECT status, COUNT(*) FROM notification_logs "
                    "WHERE created_at >= :since GROUP BY status"
                ),
                {"since": day_ago},
            )
        ).all()

    freshest_age = (
        round((now - newest_reading).total_seconds(), 1) if newest_reading else None
    )
    return {
        "generated_at": now.isoformat(),
        "telemetry": {
            "freshest_reading_at": newest_reading.isoformat() if newest_reading else None,
            "freshest_reading_age_seconds": freshest_age,
            "receiving": freshest_age is not None and freshest_age <= settings.TANK_STALE_AFTER_SECONDS,
        },
        "tanks": {
            "total": total_tanks,
            "offline": offline_tanks,
            "stale": stale_tanks,
            "never_reported": never_seen,
            "healthy": total_tanks - offline_tanks,
        },
        "gateways": {"total": gateway_total, "online": gateway_online},
        "alarms": {"open": open_alarms, "resolved": resolved_alarms},
        "notifications_last_24h": {row[0]: row[1] for row in delivery},
        "thresholds": {
            "tank_stale_after_seconds": settings.TANK_STALE_AFTER_SECONDS,
            "gateway_stale_after_seconds": settings.GATEWAY_STALE_AFTER_SECONDS,
        },
    }


@router.get("/api/v1/metrics/health-brief")
async def health_brief() -> Response:
    """Unauthenticated one-line summary for a load balancer or uptime check.

    Deliberately coarse: it reveals only whether telemetry is currently arriving
    and how many devices are offline. Detailed metrics require an admin token.
    """
    from sqlalchemy import func, select

    from fmp.core.database import async_session_factory
    from fmp.models import Tank

    now = datetime.now(UTC)
    async with async_session_factory() as session:
        newest = (
            await session.execute(text("SELECT MAX(timestamp) FROM measurements"))
        ).scalar_one()
        offline = (
            await session.execute(
                select(func.count()).select_from(Tank).where(
                    Tank.deleted_at.is_(None), Tank.connection_status == "offline"
                )
            )
        ).scalar_one()

    age = round((now - newest).total_seconds(), 1) if newest else None
    receiving = age is not None and age <= settings.TANK_STALE_AFTER_SECONDS
    # A platform that is running but not receiving telemetry is degraded: it can
    # still serve the UI, so this reports 200 with an explicit flag rather than
    # failing the health check and triggering a restart loop.
    body = {
        "status": "ok",
        "telemetry_age_seconds": age,
        "telemetry_receiving": receiving,
        "tanks_offline": offline,
    }
    return Response(content=json.dumps(body), media_type="application/json", status_code=200)