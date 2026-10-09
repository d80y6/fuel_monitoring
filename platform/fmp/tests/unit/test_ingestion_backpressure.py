"""Regression tests for reading-intake backpressure.

Per-frame database connections exhausted the SQLAlchemy QueuePool (size 20 +
overflow 20) once a burst delivered ~40 concurrent frames; every frame in the
burst then failed with ``TimeoutError`` and telemetry was silently lost.
Reading frames are queued and drained over a single connection instead.
"""

from __future__ import annotations

import asyncio

import pytest

from fmp.ingestion import main as ing


@pytest.fixture(autouse=True)
def _clear_queue():
    while not ing._READ_QUEUE.empty():
        ing._READ_QUEUE.get_nowait()
    ing._dropped_reading_frames = 0
    yield
    while not ing._READ_QUEUE.empty():
        ing._READ_QUEUE.get_nowait()


def test_enqueue_does_not_touch_the_database(monkeypatch):
    """_route must hand a reading to the queue instead of opening a session."""
    called = False

    async def _fail(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("queueing must not open a database session")

    monkeypatch.setattr(ing, "async_session_factory", _fail)

    for index in range(500):
        ing._enqueue_reading({"pressure": 1.0 + index}, "AA:00:00:00:00:01")

    assert ing._READ_QUEUE.qsize() == 500
    assert called is False


def test_queue_overflow_is_reported_not_silently_swallowed(monkeypatch):
    # Swap the queue rather than assigning the module attribute, so the real
    # 50k-frame queue is restored for the remaining tests.
    monkeypatch.setattr(ing, "_READ_QUEUE", asyncio.Queue(maxsize=4))
    for index in range(9):
        ing._enqueue_reading({"pressure": float(index)}, "AA:00:00:00:00:02")

    assert ing._READ_QUEUE.qsize() == 4
    assert ing._dropped_reading_frames == 5


async def test_batch_flush_uses_one_connection_for_the_whole_batch(monkeypatch):
    """A burst must reuse a single session, not one session per frame."""
    opened = 0
    processed: list[tuple] = []

    class _Savepoint:
        async def commit(self):
            return None

        async def rollback(self):
            return None

    class _Session:
        def __init__(self):
            self.savepoints = 0
            self.bulk_inserts = []

        async def begin_nested(self):
            self.savepoints += 1
            return _Savepoint()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    sessions: list = []

    def factory():
        nonlocal opened
        opened += 1
        session = _Session()
        sessions.append(session)
        return session

    async def fake_process(db_session, redis, payload, **kwargs):
        assert db_session is not None, "flusher must pass its own session in"
        assert kwargs.get("commit") is False, "flusher must defer the commit"
        assert kwargs.get("pending_rows") is not None, "batch must bulk-insert"
        kwargs["pending_rows"].append({"tank_id": "t", "pressure": 1.0})
        processed.append((payload, kwargs.get("gateway_mac")))

    async def fake_close():
        return None

    class _NoCounters:
        async def record_received(self, *a, **k):
            return None

        async def record_persisted(self, *a, **k):
            return None

        async def record_dropped(self, *a, **k):
            return None

        async def record_batch(self, *a, **k):
            return None

    monkeypatch.setattr(ing, "_counters", _NoCounters())

    class _Redis:
        client = type("C", (), {"aclose": staticmethod(fake_close)})()

    bulk: list[list[dict]] = []

    async def fake_bulk(session, rows):
        bulk.append(list(rows))

    monkeypatch.setattr(ing, "async_session_factory", factory)
    monkeypatch.setattr(ing, "RedisClient", lambda *a, **k: _Redis())
    monkeypatch.setattr(ing, "_process_reading", fake_process)
    monkeypatch.setattr(ing, "insert_measurements", fake_bulk)

    frames = [({"pressure": float(i)}, f"AA:00:00:00:00:{i:02X}") for i in range(250)]
    for frame, mac in frames:
        ing._enqueue_reading(frame, mac)

    task = asyncio.create_task(ing._flush_readings())
    await asyncio.sleep(ing.BATCH_INTERVAL_S + 0.4)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert len(processed) == 250
    assert opened == 1, f"expected a single pooled connection, opened {opened}"
    assert len(sessions) == 1, "the batch must use one pooled connection"
    assert bulk, "the batch must issue a bulk INSERT"
    assert len(bulk) == 1, f"expected one bulk statement, got {len(bulk)}"
    # One statement carrying every row, rather than one INSERT per frame: each
    # round trip to PostgreSQL costs tens of milliseconds on a loaded host.
    assert len(bulk[0]) == 250, "every frame must be carried in the bulk insert"


async def test_a_bad_frame_does_not_drop_its_batch(monkeypatch):
    processed: list[dict] = []

    class _Savepoint:
        def __init__(self, session):
            self._session = session

        async def commit(self):
            return None

        async def rollback(self):
            self._session.rollbacks += 1

    class _Session:
        def __init__(self):
            self.rollbacks = 0

        async def begin_nested(self):
            return _Savepoint(self)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def rollback(self):
            self.rollbacks += 1

        async def commit(self):
            return None

    sessions: list[_Session] = []

    def factory():
        session = _Session()
        sessions.append(session)
        return session

    async def fake_process(db_session, redis, payload, **kwargs):
        if payload.get("boom"):
            raise ValueError("corrupt frame")
        if kwargs.get("pending_rows") is not None:
            kwargs["pending_rows"].append(payload)
        processed.append(payload)

    async def fake_close():
        return None

    class _NoCounters:
        async def record_received(self, *a, **k):
            return None

        async def record_persisted(self, *a, **k):
            return None

        async def record_dropped(self, *a, **k):
            return None

        async def record_batch(self, *a, **k):
            return None

    monkeypatch.setattr(ing, "_counters", _NoCounters())

    class _Redis:
        client = type("C", (), {"aclose": staticmethod(fake_close)})()

    bulk = []

    async def fake_bulk(session, rows):
        bulk.append(list(rows))

    monkeypatch.setattr(ing, "async_session_factory", factory)
    monkeypatch.setattr(ing, "RedisClient", lambda *a, **k: _Redis())
    monkeypatch.setattr(ing, "_process_reading", fake_process)
    monkeypatch.setattr(ing, "insert_measurements", fake_bulk)

    for payload in [{"pressure": 1.0}, {"boom": True}, {"pressure": 2.0}]:
        ing._enqueue_reading(payload, "AA:00:00:00:00:03")

    task = asyncio.create_task(ing._flush_readings())
    await asyncio.sleep(ing.BATCH_INTERVAL_S + 0.4)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert processed == [{"pressure": 1.0}, {"pressure": 2.0}]
    assert sessions and sessions[0].rollbacks == 1


async def test_session_scope_opens_a_connection_only_when_unshared():
    class _Session:
        async def __aenter__(self):
            return "owned"

        async def __aexit__(self, *exc):
            return False

    opened = 0

    def factory():
        nonlocal opened
        opened += 1
        return _Session()

    original = ing.async_session_factory
    try:
        ing.async_session_factory = factory
        async with ing._session_scope("borrowed") as session:
            assert session == "borrowed"
        assert opened == 0

        async with ing._session_scope() as session:
            assert session == "owned"
        assert opened == 1
    finally:
        ing.async_session_factory = original