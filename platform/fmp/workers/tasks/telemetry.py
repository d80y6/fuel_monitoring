"""Stale-connection sweeper (audit G-103).

Telemetry that stops arriving is indistinguishable from telemetry that says
"nothing changed" unless something actively looks for silence. Before this task
``tanks.connection_status`` stayed ``online`` forever and ``last_connection``
kept whatever value it last had, so a probe that died on a Tuesday still
rendered as live the following week.

This beat task runs every ``STALE_SWEEP_INTERVAL_SECONDS`` and:

* marks a tank ``offline`` once ``last_connection`` is older than
  ``TANK_STALE_AFTER_SECONDS``, and ``online`` again once a frame arrives,
* raises a ``communication_lost`` alarm on the transition into offline so the
  silence becomes an acknowledgeable event rather than an absence an operator has
  to notice, and auto-resolves it when the device reports again,
* notifies through the configured alarm rules, using the same dedupe as the
  ingestion path so a flapping link cannot produce an alarm storm,
* applies the same rule to IoT gateways and dispenser stations.

Tanks that have measurements but no ``last_connection`` (legacy rows created
before it was recorded) are back-filled from their newest measurement, so the
first sweep judges them on real data instead of declaring the whole fleet
offline.
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from fmp.core.config import get_settings
from fmp.core.database import celery_session_factory
from fmp.models import Alarm, IoTGateway, Measurement, Site, Station, Tank
from fmp.workers.celery_app import celery_app

logger = logging.getLogger(__name__)
settings = get_settings()

COMM_LOST_TYPE = "communication_lost"
OPEN_ALARM_KEY = "alarm:open:{tank_id}:" + COMM_LOST_TYPE
LIVE_STATE_ALARMS = ("active", "acknowledged", "escalated")


async def _company_id(session, tank: Tank) -> uuid.UUID | None:
    row = (
        await session.execute(select(Site.company_id).where(Site.id == tank.site_id))
    ).first()
    return row[0] if row else None


async def _backfill_last_connection(session, tanks: list[Tank]) -> int:
    """Fill ``last_connection`` from the newest measurement for legacy tanks.

    One grouped query rather than one per tank.
    """
    missing = [t for t in tanks if t.deleted_at is None and t.last_connection is None]
    if not missing:
        return 0
    newest: dict[uuid.UUID, datetime] = {}
    rows = (
        await session.execute(
            select(Measurement.tank_id, Measurement.timestamp)
            .where(Measurement.tank_id.in_([t.id for t in missing]))
            .order_by(Measurement.timestamp.desc())
        )
    ).all()
    for tank_id, timestamp in rows:
        newest.setdefault(tank_id, timestamp)

    filled = 0
    for tank in missing:
        ts = newest.get(tank.id)
        if ts is not None:
            tank.last_connection = ts
        else:
            # No telemetry ever: seed a timestamp that is already stale so the
            # tank reads offline rather than being judged fresh.
            tank.last_connection = datetime.now(UTC) - timedelta(
                seconds=settings.TANK_STALE_AFTER_SECONDS + 1
            )
        filled += 1
    return filled


async def _raise_or_clear(
    session,
    redis,
    tank_id: uuid.UUID,
    *,
    resolved: bool,
    message: str,
) -> str | None:
    """Raise or auto-resolve ``communication_lost``. Returns 'raised'/'resolved'/None.

    Uses the same Redis open-set dedupe as threshold alarms, so a device that
    flaps online/offline produces one alarm, not one per sweep.
    """
    key = OPEN_ALARM_KEY.format(tank_id=tank_id)
    is_open = bool(await redis.client.sismember(key, "1"))

    if resolved:
        if not is_open:
            return None
        row = (
            await session.execute(
                select(Alarm)
                .where(
                    Alarm.tank_id == tank_id,
                    Alarm.type == COMM_LOST_TYPE,
                    Alarm.state.in_(LIVE_STATE_ALARMS),
                )
                .order_by(Alarm.timestamp.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        await redis.client.srem(key, "1")
        if row is None:
            # Redis said open but no live row exists (history pruned, or the set
            # outlived a restart). Still clear the key so the next outage fires.
            return None
        row.state = "resolved"
        row.resolved_at = datetime.now(UTC)
        row.resolved_message = message
        return "resolved"

    if is_open:
        return None
    await redis.client.sadd(key, "1")
    session.add(
        Alarm(
            tank_id=tank_id,
            timestamp=datetime.now(UTC),
            type=COMM_LOST_TYPE,
            level="WARNING",
            message=message,
            value=None,
        )
    )
    return "raised"


async def _notify(session, *, tank: Tank, company_id: uuid.UUID | None, message: str) -> None:
    """Dispatch through the tenant's alarm rules. Never raises."""
    from fmp.services.notifications.rules import dispatch_event

    try:
        await dispatch_event(
            session,
            event_type="alarm",
            level="WARNING",
            company_id=company_id,
            site_id=tank.site_id,
            tank_id=tank.id,
            context={
                "tank": tank.name,
                "site": "",
                "level": "WARNING",
                "type": COMM_LOST_TYPE,
                "message": message,
                "event_ref": f"{tank.id}:{COMM_LOST_TYPE}",
            },
            default_message="Fuel platform: {message}",
        )
    except Exception:  # noqa: BLE001 - alerting must never break the sweep
        logger.exception("communication_lost notification failed for tank %s", tank.id)


async def _sweep_async() -> dict:
    from fmp.core.redis import RedisClient

    now = datetime.now(UTC)
    gateway_cutoff = now - timedelta(seconds=settings.GATEWAY_STALE_AFTER_SECONDS)

    result = {
        "tanks_marked_offline": 0,
        "tanks_recovered": 0,
        "tanks_backfilled": 0,
        "gateways_marked_offline": 0,
        "stations_marked_offline": 0,
        "alarms_raised": 0,
        "alarms_cleared": 0,
    }

    redis = RedisClient()
    try:
        async with celery_session_factory() as session:
            tanks = list((await session.execute(select(Tank))).scalars().all())
            result["tanks_backfilled"] = await _backfill_last_connection(session, tanks)

            for tank in tanks:
                if tank.deleted_at is not None:
                    continue

                silent_seconds = (
                    (now - tank.last_connection).total_seconds()
                    if tank.last_connection is not None
                    else float("inf")
                )
                stale = silent_seconds > settings.TANK_STALE_AFTER_SECONDS
                outcome: str | None = None

                if stale:
                    if tank.connection_status != "offline":
                        result["tanks_marked_offline"] += 1
                    tank.connection_status = "offline"
                    minutes = int(silent_seconds // 60)
                    outcome = await _raise_or_clear(
                        session,
                        redis,
                        tank.id,
                        resolved=False,
                        message=(
                            f"No telemetry for {minutes} min (stale after "
                            f"{settings.TANK_STALE_AFTER_SECONDS}s)"
                        ),
                    )
                else:
                    if tank.connection_status == "offline":
                        result["tanks_recovered"] += 1
                    tank.connection_status = "online"
                    outcome = await _raise_or_clear(
                        session,
                        redis,
                        tank.id,
                        resolved=True,
                        message=(
                            f"Device reported again; silence ended after "
                            f"{int(silent_seconds)}s"
                        ),
                    )

                if outcome == "raised":
                    result["alarms_raised"] += 1
                    minutes = int(silent_seconds // 60)
                    await _notify(
                        session,
                        tank=tank,
                        company_id=await _company_id(session, tank),
                        message=(
                            f"{tank.name}: communication lost — no telemetry for "
                            f"{minutes} minutes"
                        ),
                    )
                elif outcome == "resolved":
                    result["alarms_cleared"] += 1

            for gateway in (await session.execute(select(IoTGateway))).scalars().all():
                if gateway.last_seen is None:
                    continue
                if gateway.last_seen < gateway_cutoff:
                    if gateway.connection_status != "offline":
                        result["gateways_marked_offline"] += 1
                    gateway.connection_status = "offline"
                elif gateway.connection_status == "offline":
                    gateway.connection_status = "online"

            for station in (await session.execute(select(Station))).scalars().all():
                if station.last_heartbeat is None:
                    continue
                if station.last_heartbeat < gateway_cutoff:
                    if station.connection_status != "offline":
                        result["stations_marked_offline"] += 1
                    station.connection_status = "offline"
                elif station.connection_status == "offline":
                    station.connection_status = "online"

            await session.commit()
    finally:
        await redis.client.aclose()

    logger.info("stale sweep: %s", result)
    return result


@celery_app.task(name="telemetry.sweep_stale")
def sweep_stale() -> dict:
    """Mark silent devices offline and maintain the communication_lost alarm."""
    import asyncio

    return asyncio.run(_sweep_async())