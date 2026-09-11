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
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from fmp.core.database import celery_session_factory  # noqa: F401 (fix must exist)

# The celery engine must be a NullPool engine: one connection per session,
# created AND closed inside the same asyncio.run() loop → no cross-loop reuse.
from fmp.core.database import celery_engine
from sqlalchemy.pool import NullPool


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
    from fmp.models import GatewayCommand, IoTGateway
    from sqlalchemy import delete

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
                created_at=datetime.now(timezone.utc) - timedelta(hours=1),
            ))
            # sent, at max attempts, past next_retry_at → failed_sent branch
            session.add(GatewayCommand(
                gateway_id=gw.id,
                command_type="status_probe",
                payload_json={},
                status="sent",
                attempts=3,
                max_attempts=3,
                next_retry_at=datetime.now(timezone.utc) - timedelta(minutes=5),
            ))
            await session.commit()

    _run(_seed())


def _clear_notification_gateways() -> None:
    """Ensure no active gateways so dispatch fails fast with a pure SELECT path."""
    from fmp.models import NotificationGateway, NotificationLog
    from sqlalchemy import delete

    async def _clear() -> None:
        async with celery_session_factory() as session:
            await session.execute(delete(NotificationLog))
            await session.execute(delete(NotificationGateway))
            await session.commit()

    _run(_clear())


@pytest.fixture(scope="module", autouse=True)
def celery_schema():
    """Ensure tables exist before this module runs (idempotent)."""
    _ensure_schema()
    yield


def test_celery_engine_is_nullpool():
    """Deterministic guarantee: NOT a pooled engine, so no cross-loop reuse."""
    assert isinstance(celery_engine.pool, NullPool)


def test_sweep_commands_survives_repeated_asyncio_run():
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
    """dispatch_batch_task([]) must succeed across repeated loop creations."""
    from fmp.workers.tasks.notifications import dispatch_batch_task

    for _ in range(3):
        assert dispatch_batch_task([]) == []


def test_dispatch_batch_item_exercises_celery_session():
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