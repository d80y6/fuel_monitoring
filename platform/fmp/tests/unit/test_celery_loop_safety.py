"""Celery worker loop-safety regression test.

Celery prefork workers call ``asyncio.run()`` per task, which creates AND
closes a fresh event loop on every invocation. The main engine's shared
connection pool binds asyncpg connections to the loop they were created on;
checking such a connection out on a later loop raises:

    RuntimeError: Event loop is closed
    RuntimeError: Task <Task pending ...> attached to a different loop

This module drives the CELERY-specific NullPool factory
(``celery_session_factory`` / ``celery_engine``) through the real task
wrappers (``sweep_commands`` / ``dispatch_batch_task``) repeatedly in the SAME
process. Each call owns its own loop, so any pooled/cross-loop reuse fails the
test. These are SYNC tests on purpose: the Celery task functions are sync
entry points that call ``asyncio.run()`` internally, exactly like the worker.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy.pool import NullPool

from fmp.core.database import celery_engine, celery_session_factory


class UnsafeTestTarget(RuntimeError):
    """Raised when a destructive test would target a non-disposable database."""


_GUARD_MESSAGE = (
    "Refusing to run: destructive Celery tests require FMP_TEST_INFRA=1 "
    "and an engine targeting the disposable fuel_test database."
)


def _require_test_database() -> None:
    """Refuse to run destructive cleanup against a non-test database (G-118).

    Raises :class:`UnsafeTestTarget` rather than exiting the process: these tests
    delete rows, so they must never touch a real database — but they must also not
    abort the rest of the session. The caller decides whether that means skipping
    (module fixture) or failing.
    """
    if os.getenv("FMP_TEST_INFRA") != "1" or celery_engine.url.database != "fuel_test":
        raise UnsafeTestTarget(_GUARD_MESSAGE)


def _run(coro):
    """Run a coroutine the way Celery does: a brand-new, then closed, loop."""
    return asyncio.run(coro)


def _ensure_schema() -> None:
    """Create all tables (idempotent) through the CELERY engine."""
    import fmp.models  # noqa: F401  (register all model tables)
    from fmp.core.database import Base

    async def _setup() -> None:
        async with celery_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    _run(_setup())


def _seed_gateway_rows() -> None:
    """Fresh gateway_commands rows that exercise non-Redis sweep branches."""
    from sqlalchemy import delete

    from fmp.models import GatewayCommand, IoTGateway

    async def _seed() -> None:
        async with celery_session_factory() as session:
            await session.execute(delete(GatewayCommand))
            await session.execute(delete(IoTGateway))
            await session.commit()

            gw = IoTGateway(
                gateway_mac=f"AA:BB:CC:DD:EE:{uuid.uuid4().hex[:2].upper()}",
                name="LoopTestGW",
                is_active=True,
            )
            session.add(gw)
            await session.flush()

            # pending, stuck past TTL → failed_pending branch (no Redis)
            session.add(GatewayCommand(
                gateway_id=gw.id,
                command_type="reboot",
                payload_json={},
                status="pending",
                created_at=datetime.now(UTC) - timedelta(hours=1),
            ))
            # sent, at max attempts, past next_retry_at → failed_sent branch
            session.add(GatewayCommand(
                gateway_id=gw.id,
                command_type="status_probe",
                payload_json={},
                status="sent",
                attempts=3,
                max_attempts=3,
                next_retry_at=datetime.now(UTC) - timedelta(minutes=5),
            ))
            await session.commit()

    _run(_seed())


def _clear_notification_gateways() -> None:
    """Ensure no active gateways so dispatch fails fast with a pure SELECT path."""
    from sqlalchemy import delete

    from fmp.models import NotificationGateway, NotificationLog

    async def _clear() -> None:
        async with celery_session_factory() as session:
            await session.execute(delete(NotificationLog))
            await session.execute(delete(NotificationGateway))
            await session.commit()

    _run(_clear())


@pytest.fixture(scope="module")
def celery_schema():
    """Ensure tables exist before this module runs (idempotent).

    Skips (does not abort the session) when the engine is not pointed at the
    disposable test database.
    """
    try:
        _require_test_database()
    except UnsafeTestTarget as exc:
        pytest.skip(str(exc))
    _ensure_schema()
    yield


@pytest.mark.parametrize(
    ("opt_in", "configured_database", "engine_database"),
    [
        (None, "fuel_test", "fuel_test"),
        ("0", "fuel_test", "fuel_test"),
        ("1", "fuel_test", "fuel_monitoring"),
        ("1", "postgres", "postgres"),
        ("1", "circle_test", "circle_test"),
    ],
)
def test_database_guard_rejects_unsafe_targets(
    monkeypatch, opt_in, configured_database, engine_database,
):
    from types import SimpleNamespace

    from sqlalchemy.engine import URL

    monkeypatch.setenv("POSTGRES_DB", configured_database)
    if opt_in is None:
        monkeypatch.delenv("FMP_TEST_INFRA", raising=False)
    else:
        monkeypatch.setenv("FMP_TEST_INFRA", opt_in)
    monkeypatch.setitem(
        globals(), "celery_engine",
        SimpleNamespace(url=URL.create("postgresql", database=engine_database)),
    )
    with pytest.raises(UnsafeTestTarget, match="Refusing to run"):
        _require_test_database()


def test_database_guard_accepts_explicit_test_target(monkeypatch):
    from types import SimpleNamespace

    from sqlalchemy.engine import URL

    monkeypatch.setenv("FMP_TEST_INFRA", "1")
    monkeypatch.setitem(
        globals(), "celery_engine",
        SimpleNamespace(url=URL.create("postgresql", database="fuel_test")),
    )
    _require_test_database()


def test_celery_engine_is_nullpool():
    """Deterministic guarantee: NOT a pooled engine, so no cross-loop reuse."""
    assert isinstance(celery_engine.pool, NullPool)


def test_sweep_commands_survives_repeated_asyncio_run(celery_schema):
    """5 consecutive sweep_commands() calls, each a fresh loop, must all pass."""
    from fmp.workers.tasks.commands import sweep_commands

    _seed_gateway_rows()

    results = []
    for _ in range(5):
        result = sweep_commands()
        results.append(result)
        assert isinstance(result, dict)
        assert set(result) == {"retried", "failed_sent", "failed_pending"}
        assert all(isinstance(v, int) for v in result.values())

    # First run swept the seeded rows; later runs found nothing but still
    # checked out / closed a celery-engine connection on their own loops.
    assert results[0]["failed_sent"] == 1
    assert results[0]["failed_pending"] == 1
    assert results[0]["retried"] == 0


def test_dispatch_batch_empty_survives_repeated_asyncio_run():
    try:
        _require_test_database()
    except UnsafeTestTarget as exc:
        pytest.skip(str(exc))
    """dispatch_batch_task([]) must succeed across repeated loop creations."""
    from fmp.workers.tasks.notifications import dispatch_batch_task

    for _ in range(3):
        assert dispatch_batch_task([]) == []


def test_dispatch_batch_item_exercises_celery_session(celery_schema):
    """A single item drives the celery-session SELECT path (gateway lookup)."""
    from fmp.workers.tasks.notifications import dispatch_batch_task

    _clear_notification_gateways()
    payload = {
        "allocation_id": str(uuid.uuid4()),
        "employee_id": "EMP-001",
        "employee_name": "Test User",
        "phone": "+254700000000",
        "code": "ABC123",
        "liters": 10.0,
    }

    for _ in range(3):
        results = dispatch_batch_task([payload])
        assert len(results) == 1
        assert results[0]["status"] == "FAILED"
        assert results[0]["error"] == "no active notification gateway configured"