"""Ingestion pipeline: raw sensor reading -> calibrated tank data -> alarms -> live feed.

Composes the pure ``fmp.ingestion.processor`` math with persistence (batch writer)
and realtime publishing. A single worker process holds per-tank smoothing state
(EMA + anomaly window); the writer batches inserts for TimescaleDB.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import object_session

from fmp.core.config import get_settings
from fmp.ingestion.processor import EMA, MADAnomalyDetector

settings = get_settings()

logger = logging.getLogger(__name__)

# Gasoline defaults when a tank has no configured fuel_type.
DEFAULT_DENSITY_KG_M3 = 750.0
DEFAULT_EXPANSION_COEFF = 0.00095
_WARNED_NO_FUEL_TYPE: set[uuid.UUID] = set()

LIVE_CHANNEL = "telemetry:live"
ALARMS_CHANNEL = "alarms:live"

ALARM_LEVELS = {"WARNING", "CRITICAL"}

#: A derived level may exceed the physical height only by this factor before it
#: is treated as a measurement fault rather than an overfill. 1.05 leaves room
#: for a probe mounted slightly above the tank floor.
OVER_RANGE_TOLERANCE = 1.05

#: Bit OR-ed into ``measurements.status`` when a frame is implausible.
OVER_RANGE_STATUS_BIT = 0b10


@dataclass
class AlarmCandidate:
    type: str
    level: str
    message: str
    value: float


@dataclass
class TankTelemetryState:
    """Per-tank smoothing/anomaly state held across readings."""

    pressure_ema: EMA = field(default_factory=lambda: EMA(span=10))
    anomaly: MADAnomalyDetector = field(default_factory=lambda: MADAnomalyDetector(window=8))


@dataclass(frozen=True)
class ProcessedReading:
    tank_id: uuid.UUID
    timestamp: str
    pressure: float
    temperature: float
    level: float
    volume: float
    gov_volume: float
    net_volume: float
    density_at_temperature: float
    fill_percent: float
    is_outlier: bool
    alarms: tuple = ()


#: (alarm type, level, attribute holding the threshold, value fed to the rule)
LEVEL_RULES: tuple[tuple[str, str, str], ...] = (
    ("critical_level", "CRITICAL", "critical_level_threshold"),
    ("low_level", "WARNING", "low_level_threshold"),
    ("high_level", "WARNING", "high_level_threshold"),
)
VOLUME_RULES: tuple[tuple[str, str, str], ...] = (
    ("low_volume", "WARNING", "low_volume_threshold"),
    ("high_volume", "WARNING", "high_volume_threshold"),
)


def _is_violated(alarm_type: str, value: float, threshold: float,
                 hysteresis_m: float = 0.0, hysteresis_l: float = 0.0) -> bool:
    """Threshold test with hysteresis so a value sitting on the line cannot flap.

    Raise uses a plain comparison; clear backs off by the hysteresis band, so an
    alarm only resolves once the measurement is meaningfully back inside the
    safe band (industry practice — avoids alarm storms on a noisy signal).
    """
    if alarm_type in ("low_level", "critical_level"):
        return value <= threshold
    if alarm_type == "high_level":
        return value >= threshold + hysteresis_m
    if alarm_type == "low_volume":
        return value <= threshold - hysteresis_l
    if alarm_type == "high_volume":
        return value >= threshold + hysteresis_l
    raise ValueError(f"unknown alarm type {alarm_type}")


def evaluate_alarm_rules(tank, level: float, volume: float, fill_percent: float) -> list[AlarmCandidate]:
    """Return alarm candidates for thresholds currently crossed by this reading.

    Only *raised* conditions are returned; the caller resolves previously raised
    alarms once ``_is_violated`` goes false for them.
    """
    candidates: list[AlarmCandidate] = []
    for alarm_type, alarm_level, attr in LEVEL_RULES:
        threshold = getattr(tank, attr, None)
        if threshold is not None and _is_violated(alarm_type, level, float(threshold)):
            candidates.append(AlarmCandidate(
                type=alarm_type, level=alarm_level,
                message=f"Level {level:.3f} m crossed {attr.replace('_threshold', '')} "
                        f"threshold {threshold} m",
                value=round(level, 3),
            ))
    for alarm_type, alarm_level, attr in VOLUME_RULES:
        threshold = getattr(tank, attr, None)
        if threshold is not None and _is_violated(alarm_type, volume, float(threshold)):
            candidates.append(AlarmCandidate(
                type=alarm_type, level=alarm_level,
                message=f"Volume {volume:.1f} L crossed {attr.replace('_threshold', '')} "
                        f"threshold {threshold} L",
                value=round(volume, 1),
            ))
    return candidates


def _open_alarm_key(tank_id: uuid.UUID, alarm_type: str) -> str:
    return f"alarm:open:{tank_id}:{alarm_type}"


async def load_strapping(tank) -> dict | None:
    """Load a tank's calibration table in the shape the geometry math expects.

    ``custom_strapping`` tanks used to reach ``calculate_volume`` with no table,
    whose ``ValueError("custom_strapping requires a strapping table")" was
    swallowed by the per-tank ``except`` — silently dropping every reading of
    every custom-strapping tank (G-102).
    """
    if getattr(tank, "tank_shape", None) != "custom_strapping":
        return None
    from fmp.models import StrappingTable

    session = object_session(tank)
    if session is None:
        return None
    table = await session.get(StrappingTable, tank.strapping_table_id) if tank.strapping_table_id else None
    if table is None:
        result = await session.execute(
            select(StrappingTable).where(StrappingTable.tank_id == tank.id)
        )
        table = result.scalars().first()
    if table is None:
        logger.error(
            "tank %s is custom_strapping but has no strapping table; readings cannot be "
            "converted to volume and will be rejected rather than silently mis-measured",
            tank.id,
        )
        return None
    return {
        "points": [
            {"height": float(p["height"]), "volume": float(p["volume"])}
            for p in (table.calibration_data or [])
        ],
        "method": table.interpolation_method or "linear",
    }


class IngestionPipeline:
    """Processes tank sensor telemetry and persists it via the batch writer.

    ``on_event`` is an async callback invoked for every processed reading — the
    caller (ingestion service) uses it to publish to the realtime channel.
    """

    def __init__(self, write_batch: bool = True) -> None:
        self._tank_states: dict[uuid.UUID, TankTelemetryState] = {}
        self._write_batch = write_batch

    def state_for(self, tank_id: uuid.UUID) -> TankTelemetryState:
        return self._tank_states.setdefault(tank_id, TankTelemetryState())

    async def _resolve_cleared(
        self, session, redis, tank, level: float, volume: float, raised: set[str]
    ) -> list:
        """Resolve open alarms whose condition no longer holds. Returns the rows."""
        from sqlalchemy import select

        from fmp.models import Alarm

        resolved: list = []
        checks = (
            [(t, attr, level, settings.ALARM_CLEAR_HYSTERESIS_METERS, "m")
             for t, _lvl, attr in LEVEL_RULES]
            + [(t, attr, volume, settings.ALARM_CLEAR_HYSTERESIS_LITERS, "L")
               for t, _lvl, attr in VOLUME_RULES]
        )
        # sensor_fault is not threshold-driven: it is raised when the derived
        # level is impossible and must clear as soon as a plausible frame lands.
        checks.append(("sensor_fault", None, level, 0.0, "m"))

        for alarm_type, attr, value, hysteresis, unit in checks:
            if attr is not None:
                threshold = getattr(tank, attr, None)
                if threshold is None:
                    continue
                still_violated = _is_violated(
                    alarm_type, value, float(threshold), hysteresis, hysteresis
                )
            else:
                threshold = None
                # "sensor_fault" stays violated while the reading is still over-range;
                # `raised` tells us whether this frame tripped it again.
                still_violated = alarm_type in raised

            open_key = _open_alarm_key(tank.id, alarm_type)
            if not await redis.client.sismember(open_key, "1"):
                continue
            if still_violated:
                continue
            row = (
                await session.execute(
                    select(Alarm)
                    .where(
                        Alarm.tank_id == tank.id,
                        Alarm.type == alarm_type,
                        Alarm.state.in_(("active", "acknowledged", "escalated")),
                    )
                    .order_by(Alarm.timestamp.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            await redis.client.srem(open_key, "1")
            if row is None:
                # Redis said open but no live row exists (history pruned or a
                # restart lost the set): still clear the dedupe key so the next
                # violation can fire again.
                continue
            row.state = "resolved"
            row.resolved_at = datetime.now(UTC)
            if threshold is None:
                row.resolved_message = (
                    f"Measurement back within the tank geometry: level {value} {unit}"
                )
            else:
                row.resolved_message = (
                    f"Condition cleared: value {value:.3f} {unit} back inside the safe band "
                    f"(threshold {threshold}, hysteresis {hysteresis})"
                )
            resolved.append(row)
        return resolved

    async def process(
        self,
        session,
        redis,
        tank,
        *,
        pressure: float,
        temperature: float | None,
        status: int = 0,
        captured_at=None,
        company_id: str | None = None,
        defer_insert: bool = False,
        pending_rows: list[dict] | None = None,
    ) -> ProcessedReading | None:
        """Run a single reading through calibration -> smoothing -> alarms -> persist.

        ``company_id`` is the tank's tenant; it is stamped on every realtime event
        so subscribers only receive their own data (G-003).
        """
        from fmp.ingestion.batch_writer import insert_measurements
        from fmp.ingestion.processor import (
            calculate_volume,
            density_at_temperature,
            fill_percent,
            net_standard_volume,
            pressure_to_level,
        )

        state = self.state_for(tank.id)

        try:
            if getattr(tank, "fuel_type", None) is not None:
                base_density = tank.fuel_type.base_density
                expansion_coeff = tank.fuel_type.thermal_expansion_coeff
            else:
                base_density = DEFAULT_DENSITY_KG_M3
                expansion_coeff = DEFAULT_EXPANSION_COEFF
                tank_id = tank.id
                if tank_id not in _WARNED_NO_FUEL_TYPE:
                    _WARNED_NO_FUEL_TYPE.add(tank_id)
                    logger.warning("tank %s has no fuel_type; using gasoline defaults", tank_id)
                else:
                    logger.debug("tank %s has no fuel_type; using gasoline defaults", tank_id)
            density = density_at_temperature(base_density, expansion_coeff, temperature)

            level = pressure_to_level(
                pressure_bar=pressure,
                atmospheric_bar=tank.atmospheric_pressure or 0.0,
                density=density,
                elevation=tank.elevation,
                calibration_factor=tank.calibration_factor,
            )
            is_outlier = state.anomaly.update(level)
            level = state.pressure_ema.update(level)

            # Over-range detection (data quality).
            #
            # Hydrostatics can only produce a level greater than the tank's own
            # height if the probe is misconfigured, the density assumption is
            # wrong, or the frame is corrupt. Previously this was silently
            # clamped by the geometry math, so the tank read "100% full" from an
            # impossible measurement and no sensor fault was ever raised. Such a
            # frame is now clamped for display, flagged, and reported as a
            # sensor_fault alarm instead of being believed.
            tank_height = tank.tank_height or (
                tank.tank_diameter if (tank.tank_shape or "vertical_cylinder") == "vertical_cylinder" else None
            )
            derived_level = level
            over_range = (
                tank_height is not None
                and tank_height > 0
                and derived_level > tank_height * OVER_RANGE_TOLERANCE
            )
            if over_range:
                logger.warning(
                    "tank %s over-range: derived level %.3f m exceeds height %.3f m "
                    "(pressure %.3f bar); clamping and flagging as a sensor fault",
                    tank.id, derived_level, tank_height, pressure,
                )
                level = round(tank_height, 3)
                # Discard the poisoned smoothing state: an EMA that absorbed an
                # impossible level would keep reporting it after the probe is
                # fixed, so the sensor_fault alarm could not clear.
                state.pressure_ema.reset()
                state.anomaly.reset()

            gov = calculate_volume(
                level=level,
                orientation=tank.tank_orientation,
                tank_diameter=tank.tank_diameter,
                tank_length=tank.tank_length,
                tank_height=tank.tank_height,
                tank_shape=getattr(tank, "tank_shape", None),
                tank_width=getattr(tank, "tank_width", None),
                dish_depth=getattr(tank, "dish_depth", None),
                strapping=await load_strapping(tank),
            )
            # volume == GOV (liters at current temperature); kept as the legacy field name
            volume = gov
            nsv = net_standard_volume(gov, expansion_coeff, temperature)
            percent = fill_percent(gov, tank.total_capacity_liters)
            candidates = evaluate_alarm_rules(tank, level, volume, percent)
            if over_range:
                candidates.append(AlarmCandidate(
                    type="sensor_fault", level="WARNING",
                    message=(
                        f"Measured level {derived_level} m exceeds the tank height "
                        f"{tank_height} m at {pressure} bar — check the probe, the "
                        f"fuel density or the tank geometry"
                    ),
                    value=round(derived_level, 3),
                ))

            # --- raise: dedupe on the Redis open-set so a condition that stays
            #     true produces exactly one alarm, not one per frame.
            fired_alarms = []
            for cand in candidates:
                open_key = _open_alarm_key(tank.id, cand.type)
                if not await redis.client.sismember(open_key, "1"):
                    await redis.client.sadd(open_key, "1")
                    fired_alarms.append(cand)

            # --- resolve: conditions that are no longer true (G-004). Without
            #     this the open-set never clears and each alarm type can only
            #     ever fire once per Redis lifetime.
            resolved = await self._resolve_cleared(
                session, redis, tank, level, volume, raised={c.type for c in candidates}
            )

            if fired_alarms or resolved:
                from datetime import datetime

                from fmp.models import Alarm

                at = captured_at or datetime.now(UTC)
                for cand in fired_alarms:
                    session.add(Alarm(
                        tank_id=tank.id, timestamp=at, type=cand.type,
                        level=cand.level, message=cand.message, value=cand.value,
                    ))
                    await publish_alarm(redis, tank, cand, at, company_id=company_id,
                                         state="active")
                for alarm in resolved:
                    await publish_alarm_resolution(redis, tank, alarm, at,
                                                   company_id=company_id)

            if self._write_batch:
                read = {
                    "timestamp": captured_at,
                    "tank_id": tank.id,
                    "pressure": pressure,
                    "temperature": temperature,
                    "level": level,
                    # 2 = over-range / implausible measurement (see OVER_RANGE_TOLERANCE)
                    "status": status | (OVER_RANGE_STATUS_BIT if over_range else 0),
                    "volume": volume,
                    "gov_volume": gov,
                    "net_volume": nsv,
                    "density_at_temperature": density,
                    "fill_percent": percent,
                    "is_outlier": is_outlier,
                }
                if defer_insert and pending_rows is not None:
                    # Hand the row back so the caller can insert the whole batch in
                    # one statement. Round-trip latency to PostgreSQL dominates
                    # this path on a loaded host (~57 ms even for SELECT 1), so a
                    # per-frame INSERT caps throughput no matter how little work
                    # the frame itself does.
                    pending_rows.append(read)
                else:
                    await insert_measurements(session, [read])

            return ProcessedReading(
                tank_id=tank.id,
                timestamp=captured_at.isoformat() if captured_at else None,
                pressure=pressure,
                temperature=temperature or 0.0,
                level=level,
                volume=volume,
                gov_volume=gov,
                net_volume=nsv,
                density_at_temperature=density,
                fill_percent=percent,
                is_outlier=is_outlier,
                alarms=tuple(fired_alarms),
            )
        except Exception:  # never let one bad tank stall the stream
            logger.exception("pipeline error for tank %s", tank.id)
            return None


async def publish_live(redis, reading: ProcessedReading, *, company_id=None):
    """Fan out a processed reading to the realtime channel (JSON payload)."""
    await redis.publish(LIVE_CHANNEL, {
        "tank_id": str(reading.tank_id),
        "company_id": company_id,
        "timestamp": reading.timestamp,
        "pressure": reading.pressure,
        "temperature": reading.temperature,
        "level": reading.level,
        "volume": reading.volume,
        "gov_volume": reading.gov_volume,
        "net_volume": reading.net_volume,
        "density_at_temperature": reading.density_at_temperature,
        "fill_percent": reading.fill_percent,
        "is_outlier": reading.is_outlier,
        "alarms": [{"type": a.type, "level": a.level, "message": a.message} for a in reading.alarms],
    })


async def publish_alarm(redis, tank, alarm: AlarmCandidate, at=None, *, company_id=None,
                        state: str = "active"):
    """Fan out a newly-raised alarm to the realtime alarms channel."""
    await redis.publish(ALARMS_CHANNEL, {
        "type": alarm.type,
        "level": alarm.level,
        "message": alarm.message,
        "value": alarm.value,
        "tank_id": str(tank.id),
        "company_id": company_id,
        "state": state,
        "timestamp": (at or datetime.now(UTC)).isoformat(),
    })


async def publish_alarm_resolution(redis, tank, alarm, at=None, *, company_id=None):
    """Fan out an automatic resolution so live clients clear the alarm."""
    await redis.publish(ALARMS_CHANNEL, {
        "type": alarm.type,
        "level": alarm.level,
        "message": alarm.resolved_message or "condition cleared",
        "value": alarm.value,
        "tank_id": str(tank.id),
        "alarm_id": str(alarm.id),
        "company_id": company_id,
        "state": "resolved",
        "timestamp": (at or datetime.now(UTC)).isoformat(),
    })