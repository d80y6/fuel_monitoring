"""Ingestion pipeline: raw sensor reading -> calibrated tank data -> alarms -> live feed.

Composes the pure ``fmp.ingestion.processor`` math with persistence (batch writer)
and realtime publishing. A single worker process holds per-tank smoothing state
(EMA + anomaly window); the writer batches inserts for TimescaleDB.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from fmp.ingestion.processor import EMA, MADAnomalyDetector

logger = logging.getLogger(__name__)

# Gasoline defaults when a tank has no configured fuel_type.
DEFAULT_DENSITY_KG_M3 = 750.0
DEFAULT_EXPANSION_COEFF = 0.00095
_WARNED_NO_FUEL_TYPE: set[uuid.UUID] = set()

LIVE_CHANNEL = "telemetry:live"
ALARMS_CHANNEL = "alarms:live"

ALARM_LEVELS = {"WARNING", "CRITICAL"}


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


def evaluate_alarm_rules(tank, level: float, volume: float, fill_percent: float) -> list[AlarmCandidate]:
    """Return alarm candidates (deduplicated by the caller) for crossed thresholds."""
    candidates: list[AlarmCandidate] = []

    if tank.low_level_threshold is not None and level <= tank.low_level_threshold:
        candidates.append(AlarmCandidate(
            type="low_level", level="WARNING",
            message=f"Level {level:.3f} m below low threshold {tank.low_level_threshold} m",
            value=round(level, 3),
        ))
    if tank.critical_level_threshold is not None and level <= tank.critical_level_threshold:
        candidates.append(AlarmCandidate(
            type="critical_level", level="CRITICAL",
            message=f"Level {level:.3f} m at/below critical threshold {tank.critical_level_threshold} m",
            value=round(level, 3),
        ))
    if tank.high_level_threshold is not None and level >= tank.high_level_threshold:
        candidates.append(AlarmCandidate(
            type="high_level", level="WARNING",
            message=f"Level {level:.3f} m above high threshold {tank.high_level_threshold} m",
            value=round(level, 3),
        ))
    if tank.low_volume_threshold is not None and volume <= tank.low_volume_threshold:
        candidates.append(AlarmCandidate(
            type="low_volume", level="WARNING",
            message=f"Volume {volume:.1f} L below low threshold {tank.low_volume_threshold} L",
            value=round(volume, 1),
        ))
    if tank.high_volume_threshold is not None and volume >= tank.high_volume_threshold:
        candidates.append(AlarmCandidate(
            type="high_volume", level="WARNING",
            message=f"Volume {volume:.1f} L above high threshold {tank.high_volume_threshold} L",
            value=round(volume, 1),
        ))
    return candidates


def _open_alarm_key(tank_id: uuid.UUID, alarm_type: str) -> str:
    return f"alarm:open:{tank_id}:{alarm_type}"


class IngestionPipeline:
    """Processes tank sensor telemetry and persists it via the batch writer.

    ``on_event`` is an async callback invoked for every processed reading — the
    caller (ingestion service) uses it to publish to the realtime channel.
    """

    def __init__(self, write_batch: bool = True) -> None:
        self._tank_states: dict[uuid.UUID, TankTelemetryState] = {}
        self._write_batch = write_batch
        self._pending: list[dict] = []

    def state_for(self, tank_id: uuid.UUID) -> TankTelemetryState:
        return self._tank_states.setdefault(tank_id, TankTelemetryState())

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
    ) -> ProcessedReading | None:
        """Run a single reading through calibration -> smoothing -> alarms -> persist."""
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

            gov = calculate_volume(
                level=level,
                orientation=tank.tank_orientation,
                tank_diameter=tank.tank_diameter,
                tank_length=tank.tank_length,
                tank_height=tank.tank_height,
                tank_shape=getattr(tank, "tank_shape", None),
                tank_width=getattr(tank, "tank_width", None),
                dish_depth=getattr(tank, "dish_depth", None),
            )
            # volume == GOV (liters at current temperature); kept as the legacy field name
            volume = gov
            nsv = net_standard_volume(gov, expansion_coeff, temperature)
            percent = fill_percent(gov, tank.total_capacity_liters)
            candidates = evaluate_alarm_rules(tank, level, volume, percent)

            fired_alarms = []
            for cand in candidates:
                open_key = _open_alarm_key(tank.id, cand.type)
                if not await redis.client.sismember(open_key, "1"):
                    await redis.client.sadd(open_key, "1")
                    fired_alarms.append(cand)

            if fired_alarms:
                from datetime import datetime, timezone

                from fmp.models import Alarm

                at = captured_at or datetime.now(timezone.utc)
                for cand in fired_alarms:
                    session.add(Alarm(
                        tank_id=tank.id, timestamp=at, type=cand.type,
                        level=cand.level, message=cand.message, value=cand.value,
                    ))
                    await publish_alarm(redis, tank, cand, at)

            if self._write_batch:
                read = {
                    "timestamp": captured_at,
                    "tank_id": tank.id,
                    "pressure": pressure,
                    "temperature": temperature,
                    "level": level,
                    "volume": volume,
                    "gov_volume": gov,
                    "net_volume": nsv,
                    "density_at_temperature": density,
                    "fill_percent": percent,
                    "is_outlier": is_outlier,
                    "status": status,
                }
                await insert_measurements(session, [read])
                self._pending.append(read)

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


async def publish_live(redis, reading: ProcessedReading):
    """Fan out a processed reading to the realtime channel (JSON payload)."""
    await redis.publish(LIVE_CHANNEL, {
        "tank_id": str(reading.tank_id),
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


async def publish_alarm(redis, tank, alarm: AlarmCandidate, at=None):
    """Fan out a newly-raised alarm to the realtime alarms channel."""
    from datetime import datetime, timezone

    await redis.publish(ALARMS_CHANNEL, {
        "type": alarm.type,
        "level": alarm.level,
        "message": alarm.message,
        "value": alarm.value,
        "tank_id": str(tank.id),
        "timestamp": (at or datetime.now(timezone.utc)).isoformat(),
    })