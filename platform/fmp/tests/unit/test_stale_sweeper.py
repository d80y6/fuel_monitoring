"""Stale-connection sweeper (G-103).

Covers the transition an operator depends on: silence becomes an acknowledgeable
alarm, and the alarm clears when the device returns. Before this task a dead
probe rendered as "online" indefinitely.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from fmp.workers.tasks.telemetry import (
    COMM_LOST_TYPE,
    OPEN_ALARM_KEY,
    _backfill_last_connection,
    _raise_or_clear,
)


class FakeRedis:
    def __init__(self):
        self.sets: dict[str, set] = {}
        self.client = self

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

    async def aclose(self):
        return None


class Session:
    """Minimal session: collects added rows, returns a queued query result."""

    def __init__(self, live_alarm=None, measurements=()):
        self.added = []
        self._live = live_alarm
        self._measurements = list(measurements)

    def add(self, row):
        self.added.append(row)

    def __init_subclass__(cls):  # pragma: no cover
        pass

    async def execute(self, *_args, **_kwargs):
        rows = list(self._measurements)
        live = self._live
        return SimpleNamespace(
            all=lambda: rows,
            scalars=lambda: SimpleNamespace(all=lambda: [], first=lambda: None),
            scalar_one_or_none=lambda: live,
        )

    async def commit(self):
        pass


def tank(**overrides):
    base = dict(
        id=uuid.uuid4(),
        name="Tank",
        site_id=uuid.uuid4(),
        deleted_at=None,
        connection_status="online",
        last_connection=datetime.now(UTC),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class TestRaiseCommunicationLost:
    @pytest.mark.asyncio
    async def test_raises_once_when_silence_is_first_detected(self):
        session = Session()
        redis = FakeRedis()
        outcome = await _raise_or_clear(
            session, redis, tank().id, resolved=False, message="silent for 12 min"
        )

        assert outcome == "raised"
        assert len(session.added) == 1
        alarm = session.added[0]
        assert alarm.type == COMM_LOST_TYPE
        assert alarm.level == "WARNING"
        assert "silent for 12 min" in alarm.message

    @pytest.mark.asyncio
    async def test_does_not_raise_again_while_already_open(self):
        """A flapping link must not produce one alarm per sweep."""
        session = Session()
        redis = FakeRedis()
        tank_id = tank().id

        first = await _raise_or_clear(
            session, redis, tank_id, resolved=False, message="first"
        )
        second = await _raise_or_clear(
            session, redis, tank_id, resolved=False, message="again"
        )

        assert first == "raised"
        assert second is None
        assert len(session.added) == 1

    @pytest.mark.asyncio
    async def test_resolves_when_the_device_reports_again(self):
        live = SimpleNamespace(
            id=uuid.uuid4(),
            state="active",
            resolved_at=None,
            resolved_message=None,
        )
        session = Session(live_alarm=live)
        redis = FakeRedis()
        tank_id = tank().id
        await _raise_or_clear(session, redis, tank_id, resolved=False, message="silent")

        outcome = await _raise_or_clear(
            session, redis, tank_id, resolved=True, message="device reported again"
        )

        assert outcome == "resolved"
        assert live.state == "resolved"
        assert live.resolved_at is not None
        assert "reported again" in live.resolved_message
        # Dedupe key cleared so a future outage fires a fresh alarm.
        assert await redis.sismember(OPEN_ALARM_KEY.format(tank_id=tank_id), "1") is False

    @pytest.mark.asyncio
    async def test_clear_is_a_no_op_when_nothing_is_open(self):
        outcome = await _raise_or_clear(
            Session(), FakeRedis(), tank().id, resolved=True, message="x"
        )
        assert outcome is None

    @pytest.mark.asyncio
    async def test_clears_the_dedupe_key_even_when_the_row_vanished(self):
        """Redis outliving the row must not block the next alarm forever."""
        session = Session(live_alarm=None)
        redis = FakeRedis()
        tank_id = tank().id
        await redis.sadd(OPEN_ALARM_KEY.format(tank_id=tank_id), "1")

        outcome = await _raise_or_clear(session, redis, tank_id, resolved=True, message="x")

        assert outcome is None
        assert await redis.sismember(OPEN_ALARM_KEY.format(tank_id=tank_id), "1") is False


class TestBackfill:
    @pytest.mark.asyncio
    async def test_fills_last_connection_from_the_newest_measurement(self):
        t = tank(last_connection=None)
        newest = datetime.now(UTC) - timedelta(minutes=3)
        session = Session(measurements=[(t.id, newest)])

        filled = await _backfill_last_connection(session, [t])

        assert filled == 1
        assert t.last_connection == newest

    @pytest.mark.asyncio
    async def test_tank_with_no_telemetry_at_all_is_marked_stale(self):
        """A tank that has never reported must read offline, not 'fresh'."""
        from fmp.core.config import get_settings

        t = tank(last_connection=None)
        session = Session(measurements=[])

        filled = await _backfill_last_connection(session, [t])

        assert filled == 1
        settings = get_settings()
        assert t.last_connection is not None
        assert t.last_connection < datetime.now(UTC) - timedelta(
            seconds=settings.TANK_STALE_AFTER_SECONDS
        )

    @pytest.mark.asyncio
    async def test_skips_tanks_that_already_have_a_timestamp(self):
        t = tank(last_connection=datetime.now(UTC))
        session = Session()
        assert await _backfill_last_connection(session, [t]) == 0

    @pytest.mark.asyncio
    async def test_ignores_soft_deleted_tanks(self):
        t = tank(last_connection=None, deleted_at=datetime.now(UTC))
        session = Session(measurements=[(t.id, datetime.now(UTC))])
        assert await _backfill_last_connection(session, [t]) == 0


class TestTaskRegistration:
    def test_sweep_task_is_named_and_scheduled(self):
        from fmp.workers.celery_app import celery_app

        schedule = celery_app.conf.beat_schedule
        assert "telemetry-sweep-stale" in schedule
        entry = schedule["telemetry-sweep-stale"]
        assert entry["task"] == "telemetry.sweep_stale"
        assert entry["schedule"] > 0