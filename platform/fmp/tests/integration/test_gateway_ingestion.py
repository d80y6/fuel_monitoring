"""Integration test: gateway provisioning, ack handler, relay publish."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from fmp.tests.conftest import FakeRedis

pytestmark = pytest.mark.asyncio


async def test_status_heartbeat_auto_registers_gateway(requires_infra, db):
    from fmp.core.database import async_session_factory
    from fmp.ingestion.main import _handle_status
    from fmp.models import IoTGateway
    from sqlalchemy import select

    await _handle_status(FakeRedis(), {"status": "online", "firmware_version": "2.1.0"},
                         "AA:BB:CC:DD:EE:77")

    async with async_session_factory() as session:
        gw = (
            await session.execute(select(IoTGateway).where(IoTGateway.gateway_mac == "AA:BB:CC:DD:EE:77"))
        ).scalar_one()
        assert gw.is_active is False
        assert gw.connection_status == "online"
        assert gw.last_seen is not None
        assert gw.firmware_version == "2.1.0"


async def test_ack_handler_updates_row_and_gateway(requires_infra, db):
    from fmp.core.database import async_session_factory
    from fmp.ingestion.main import _handle_command_ack
    from fmp.models import GatewayCommand, IoTGateway

    async with async_session_factory() as session:
        gw = IoTGateway(gateway_mac="AA:BB:CC:DD:EE:01", name="GW", is_active=True)
        session.add(gw)
        await session.flush()
        cmd = GatewayCommand(
            gateway_id=gw.id, command_type="reboot", payload_json={},
            status="sent", attempts=1, max_attempts=3,
            next_retry_at=datetime.now(timezone.utc),
        )
        session.add(cmd)
        await session.commit()
        cmd_id = str(cmd.command_id)

    await _handle_command_ack(FakeRedis(), {"command_id": cmd_id, "status": "executed"},
                              "AA:BB:CC:DD:EE:01")

    async with async_session_factory() as session:
        from sqlalchemy import select
        cmd = (await session.execute(
            select(GatewayCommand).where(GatewayCommand.command_id == cmd_id)
        )).scalar_one()
        assert cmd.status == "acked"
        assert cmd.ack_status == "executed"
        assert cmd.ack_received_at is not None
        gw = (await session.execute(
            select(IoTGateway).where(IoTGateway.id == cmd.gateway_id)
        )).scalar_one()
        assert gw.connection_status == "online"
        assert gw.last_seen is not None


async def test_unknown_ack_is_ignored(requires_infra, db):
    from fmp.core.database import async_session_factory
    from fmp.ingestion.main import _handle_command_ack
    from fmp.models import GatewayCommand
    from sqlalchemy import select

    await _handle_command_ack(
        FakeRedis(), {"command_id": str(uuid.uuid4()), "status": "executed"}, "AA:BB:CC:DD:EE:99"
    )
    async with async_session_factory() as session:
        assert (await session.execute(select(GatewayCommand))).scalars().all() == []


async def test_sweeper_requeues_then_fails(requires_infra, db):
    from datetime import timedelta

    from fmp.core.database import async_session_factory
    from fmp.core.redis import RedisClient
    from fmp.ingestion.relay import QUEUE_OUTBOUND
    from fmp.models import GatewayCommand, IoTGateway
    from fmp.workers.tasks.commands import _scan_and_sweep
    from sqlalchemy import select

    ago = datetime.now(timezone.utc) - timedelta(minutes=10)

    async with async_session_factory() as session:
        gw = IoTGateway(gateway_mac="AA:BB:CC:DD:EE:05", name="GW5", is_active=True)
        session.add(gw)
        await session.flush()
        cmd = GatewayCommand(
            gateway_id=gw.id, command_type="reboot", payload_json={},
            status="sent", attempts=1, max_attempts=3, next_retry_at=ago,
        )
        session.add(cmd)
        await session.commit()
        cmd_id = str(cmd.command_id)

    redis = RedisClient()
    await redis.client.delete(QUEUE_OUTBOUND)
    await redis.client.aclose()

    await _scan_and_sweep()

    redis = RedisClient()
    assert await redis.client.llen(QUEUE_OUTBOUND) == 1
    await redis.client.delete(QUEUE_OUTBOUND)
    await redis.client.aclose()

    # exhaust: set attempts to max so sweep fails it instead
    async with async_session_factory() as session:
        cmd = (await session.execute(
            select(GatewayCommand).where(GatewayCommand.command_id == cmd_id)
        )).scalar_one()
        cmd.attempts = 3
        cmd.next_retry_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        await session.commit()

    await _scan_and_sweep()

    async with async_session_factory() as session:
        cmd = (await session.execute(
            select(GatewayCommand).where(GatewayCommand.command_id == cmd_id)
        )).scalar_one()
        assert cmd.status == "failed"
        assert cmd.error_message