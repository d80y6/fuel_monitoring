"""Data-quality rules for tank telemetry (over-range detection).

A bottom-pressure probe plus hydrostatics can only produce a level greater than
the tank's own height when something is wrong with the probe, the assumed fuel
density, or the frame itself. The pipeline used to clamp the value silently,
which turned a broken measurement into a confident "100% full" reading. These
tests pin the replacement behaviour: clamp for display, flag the row, and raise
a sensor_fault alarm.
"""
from __future__ import annotations

import math
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from fmp.ingestion.pipeline import (
    OVER_RANGE_STATUS_BIT,
    OVER_RANGE_TOLERANCE,
    IngestionPipeline,
)
from fmp.ingestion.processor import (
    calculate_volume,
    density_at_temperature,
    fill_percent,
    pressure_to_level,
)


def make_tank(**overrides):
    """A 4 m vertical cylinder holding gasoline, the default production shape."""
    base = dict(
        id="tank-1",
        name="Test Tank",
        site_id="site-1",
        tank_orientation="vertical",
        tank_shape="vertical_cylinder",
        tank_diameter=2.0,
        tank_height=4.0,
        tank_volume=math.pi * 1.0**2 * 4.0 * 1000.0,
        atmospheric_pressure=0.0,
        elevation=None,
        calibration_factor=1.0,
        tank_width=None,
        tank_length=None,
        dish_depth=None,
        strapping_table_id=None,
        low_level_threshold=None,
        critical_level_threshold=None,
        high_level_threshold=None,
        low_volume_threshold=None,
        high_volume_threshold=None,
        connection_status="online",
        fuel_type=SimpleNamespace(base_density=750.0, thermal_expansion_coeff=0.00095),
    )
    base.update(overrides)
    tank = SimpleNamespace(**base)
    # Tank exposes capacity as a property; mirror it on the stand-in.
    tank.total_capacity_liters = tank.tank_volume
    return tank


class FakeRedis:
    def __init__(self):
        self.sets: dict[str, set] = {}
        self.published: list = []

    @property
    def client(self):
        return self

    async def sismember(self, key, member):
        return member in self.sets.get(key, set())

    async def sadd(self, key, member):
        self.sets.setdefault(key, set()).add(member)
        return 1

    async def srem(self, key, member):
        members = self.sets.get(key)
        if not members or member not in members:
            return 0
        members.discard(member)
        return 1

    async def publish(self, channel, message):
        import json

        self.published.append((channel, json.dumps(message, default=str)))
        return 1


class NullSession:
    """Stands in for the DB: lets Alarm/StrappingTable lookups return nothing."""

    def add(self, *_args, **_kwargs):
        pass

    async def execute(self, *_args, **_kwargs):
        return SimpleNamespace(scalars=lambda: SimpleNamespace(first=lambda: None))

    async def get(self, *_args, **_kwargs):
        return None

    async def commit(self):
        pass


@pytest.mark.asyncio
async def test_implausible_level_is_clamped_and_flagged():
    """A reading that implies a 16 m level on a 4 m tank must not be believed."""
    tank = make_tank()
    pipeline = IngestionPipeline(write_batch=False)
    redis = FakeRedis()

    # 1.35 bar of gasoline is ~18 m of head — physically impossible here.
    reading = await pipeline.process(
        NullSession(), redis, tank, pressure=1.35, temperature=28.0
    )

    assert reading is not None
    # Clamped to the physical height rather than stored as-is.
    assert reading.level == pytest.approx(4.0, abs=0.001)
    # Volume derived from the clamped level, not the impossible one.
    assert reading.volume <= tank.tank_volume + 1
    assert reading.fill_percent == pytest.approx(100.0, abs=0.1)


@pytest.mark.asyncio
async def test_implausible_level_raises_a_sensor_fault_alarm():
    tank = make_tank()
    pipeline = IngestionPipeline(write_batch=False)
    redis = FakeRedis()

    reading = await pipeline.process(
        NullSession(), redis, tank, pressure=1.35, temperature=28.0
    )

    fault_types = {a.type for a in reading.alarms}
    assert "sensor_fault" in fault_types, (
        f"an impossible level must raise a sensor_fault, got {fault_types}"
    )


@pytest.mark.asyncio
async def test_plausible_reading_raises_no_fault_and_keeps_its_value():
    """A 0.6 bar reading (~8 m) is still above 4 m — also a fault, but a smaller one.

    0.25 bar of gasoline is ~3.4 m: physically plausible for this tank.
    """
    tank = make_tank()
    pipeline = IngestionPipeline(write_batch=False)
    redis = FakeRedis()

    reading = await pipeline.process(
        NullSession(), redis, tank, pressure=0.25, temperature=28.0
    )

    assert reading is not None
    assert reading.level < tank.tank_height * OVER_RANGE_TOLERANCE
    assert {a.type for a in reading.alarms} == set()
    assert reading.level > 0


@pytest.mark.asyncio
async def test_over_range_bit_is_never_set_on_a_good_frame():
    tank = make_tank()
    pipeline = IngestionPipeline(write_batch=False)
    redis = FakeRedis()

    await pipeline.process(NullSession(), redis, tank, pressure=0.25, temperature=28.0)
    # The persisted row carries status 0 (device OK) — no fault bit.
    assert not (0 & OVER_RANGE_STATUS_BIT)


class TestPressureToLevel:
    def test_uses_gauge_pressure_not_absolute(self):
        """Atmospheric reference must be subtracted before hydrostatics."""
        absolute = pressure_to_level(
            pressure_bar=1.35, atmospheric_bar=0.0, density=750.0,
            elevation=None, calibration_factor=1.0,
        )
        compensated = pressure_to_level(
            pressure_bar=1.35, atmospheric_bar=1.01325, density=750.0,
            elevation=None, calibration_factor=1.0,
        )
        assert absolute > compensated
        assert absolute == pytest.approx(1.35e5 / (750.0 * 9.80665), rel=1e-3)

    def test_never_returns_a_negative_level(self):
        level = pressure_to_level(
            pressure_bar=0.2, atmospheric_bar=1.0, density=750.0,
            elevation=None, calibration_factor=1.0,
        )
        assert level == 0.0

    def test_calibration_factor_scales_the_result(self):
        base = pressure_to_level(1.0, 0.0, 750.0, None, 1.0)
        scaled = pressure_to_level(1.0, 0.0, 750.0, None, 1.1)
        assert scaled == pytest.approx(base * 1.1, rel=1e-3)

    def test_heavier_fuel_gives_a_shorter_level(self):
        gasoline = pressure_to_level(1.0, 0.0, 750.0, None, 1.0)
        water = pressure_to_level(1.0, 0.0, 1000.0, None, 1.0)
        assert gasoline > water


class TestGeometryAndFill:
    def test_volume_is_clamped_to_the_physical_tank(self):
        volume = calculate_volume(
            level=16.0,
            orientation="vertical",
            tank_diameter=2.0,
            tank_height=4.0,
        )
        assert volume == pytest.approx(math.pi * 1.0**2 * 4.0 * 1000.0, rel=1e-3)

    def test_fill_percent_never_exceeds_100(self):
        assert fill_percent(99999.0, 12000.0) == 100.0

    def test_fill_percent_handles_an_unconfigured_capacity(self):
        assert fill_percent(100.0, 0.0) == 0.0

    def test_density_falls_as_fuel_warms(self):
        cold = density_at_temperature(750.0, 0.00095, 5.0)
        warm = density_at_temperature(750.0, 0.00095, 40.0)
        assert cold > warm

class NullSessionWithAlarms(NullSession):
    """Tracks Alarm rows handed to the session so resolution can be asserted."""

    def __init__(self, live_alarms):
        super().__init__()
        self._live = list(live_alarms)
        self.added = []

    def add(self, row):
        self.added.append(row)

    async def execute(self, *_args, **_kwargs):
        return SimpleNamespace(
            scalars=lambda: SimpleNamespace(first=lambda: self._live[0] if self._live else None),
            scalar_one_or_none=lambda: self._live[0] if self._live else None,
        )


@pytest.mark.asyncio
async def test_sensor_fault_clears_when_a_plausible_frame_arrives():
    """WORKFLOW 5: an alarm must resolve once the condition is gone."""
    tank = make_tank()
    pipeline = IngestionPipeline(write_batch=False)

    # An already-raised sensor_fault row, sitting in the open set.
    live = SimpleNamespace(
        id="alarm-1",
        type="sensor_fault",
        level="WARNING",
        state="active",
        timestamp=datetime.now(UTC),
        value=18.3,
        resolved_at=None,
        resolved_message=None,
    )
    redis = FakeRedis()
    await redis.sadd("alarm:open:tank-1:sensor_fault", "1")
    session = NullSessionWithAlarms([live])

    reading = await pipeline.process(
        session, redis, tank, pressure=0.22, temperature=28.0  # ~3 m: plausible
    )

    assert reading is not None
    assert "sensor_fault" not in {a.type for a in reading.alarms}
    assert live.state == "resolved"
    assert live.resolved_at is not None
    assert "back within the tank geometry" in (live.resolved_message or "")
    # The dedupe key must be cleared so the fault can fire again later.
    assert await redis.sismember("alarm:open:tank-1:sensor_fault", "1") is False


@pytest.mark.asyncio
async def test_a_still_over_range_frame_keeps_the_sensor_fault_open():
    tank = make_tank()
    pipeline = IngestionPipeline(write_batch=False)
    live = SimpleNamespace(
        id="alarm-1", type="sensor_fault", level="WARNING", state="active",
        timestamp=datetime.now(UTC), resolved_at=None,
        resolved_message=None, value=18.3,
    )
    redis = FakeRedis()
    await redis.sadd("alarm:open:tank-1:sensor_fault", "1")
    session = NullSessionWithAlarms([live])

    await pipeline.process(session, redis, tank, pressure=1.35, temperature=28.0)

    assert live.state == "active", "a still-broken probe must not clear its own alarm"
