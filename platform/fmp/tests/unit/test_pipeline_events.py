"""Unit tests: IngestionPipeline publishes alarm events to the live alarm channel."""
from __future__ import annotations

import json
import uuid

import pytest

from fmp.tests.conftest import FakeRedis


class FakeSession:
    def __init__(self) -> None:
        self.added: list = []

    def add(self, obj) -> None:
        self.added.append(obj)


def _tank(**overrides):
    from fmp.models import Tank

    defaults = dict(
        id=uuid.uuid4(),
        sensor_serial_number=f"SN-{uuid.uuid4().hex[:8]}",
        tank_orientation="vertical", tank_diameter=2.0, tank_height=3.0,
        tank_volume=9200.0, elevation=0.0,
        calibration_factor=1.0,
        critical_level_threshold=0.5, low_level_threshold=1.0,
        high_level_threshold=2.8, low_volume_threshold=2000.0,
    )
    defaults.update(overrides)
    return Tank(**defaults)


@pytest.mark.asyncio
async def test_alarm_published_to_alarms_channel_on_first_crossing():
    from datetime import datetime, timezone

    from fmp.ingestion.pipeline import IngestionPipeline, ALARMS_CHANNEL

    # only the critical threshold is above the simulated level (~0.36 m)
    tank = _tank(
        low_level_threshold=0.2,
        low_volume_threshold=100.0,
    )
    redis = FakeRedis()
    pipeline = IngestionPipeline(write_batch=False)

    # one reading below critical threshold => exact critical alarm once
    r = await pipeline.process(
        FakeSession(), redis, tank,
        pressure=0.03, temperature=25.0,
        captured_at=datetime.now(timezone.utc),
    )
    assert r is not None
    assert any(a.type == "critical_level" for a in r.alarms)

    alarm_msgs = [m for ch, m in redis.published if ch == ALARMS_CHANNEL]
    assert len(alarm_msgs) == 1
    payload = json.loads(alarm_msgs[0])
    assert payload["type"] == "critical_level"
    assert payload["tank_id"] == str(tank.id)


@pytest.mark.asyncio
async def test_alarm_not_republished_while_open():
    from datetime import datetime, timezone

    from fmp.ingestion.pipeline import IngestionPipeline, ALARMS_CHANNEL

    tank = _tank(
        low_level_threshold=0.2,
        low_volume_threshold=100.0,
    )
    redis = FakeRedis()
    pipeline = IngestionPipeline(write_batch=False)

    for _ in range(3):
        await pipeline.process(
            FakeSession(), redis, tank,
            pressure=0.03, temperature=25.0,
            captured_at=datetime.now(timezone.utc),
        )

    alarm_msgs = [m for ch, m in redis.published if ch == ALARMS_CHANNEL]
    assert len(alarm_msgs) == 1


@pytest.mark.asyncio
async def test_reading_published_to_telemetry_channel():
    from datetime import datetime, timezone

    from fmp.ingestion.pipeline import IngestionPipeline, LIVE_CHANNEL, publish_live

    tank = _tank()
    redis = FakeRedis()
    pipeline = IngestionPipeline(write_batch=False)

    r = await pipeline.process(
        FakeSession(), redis, tank,
        pressure=0.125, temperature=25.0,
        captured_at=datetime.now(timezone.utc),
    )
    assert r is not None
    await publish_live(redis, r)
    msgs = [m for ch, m in redis.published if ch == LIVE_CHANNEL]
    assert len(msgs) == 1
    payload = json.loads(msgs[0])
    assert payload["tank_id"] == str(tank.id)
    assert "volume" in payload and "fill_percent" in payload