"""Celery task: TTL sweeper for gateway commands (retry → fail)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from fmp.core.config import get_settings
from fmp.core.database import async_session_factory
from fmp.core.redis import RedisClient
from fmp.ingestion.relay import enqueue_command, next_retry_datetime
from fmp.models import GatewayCommand
from fmp.workers.celery_app import celery_app

settings = get_settings()


async def _scan_and_sweep() -> dict[str, int]:
    now = datetime.now(timezone.utc)
    pending_cutoff = now - timedelta(seconds=settings.COMMAND_PENDING_TTL_SECONDS)
    retried = failed_sent = failed_pending = 0

    async with async_session_factory() as session:
        # sent but past next_retry_at and under max attempts → requeue
        q = (
            select(GatewayCommand)
            .options(selectinload(GatewayCommand.gateway))
            .where(
                GatewayCommand.status == "sent",
                GatewayCommand.next_retry_at.is_not(None),
                GatewayCommand.next_retry_at < now,
                GatewayCommand.attempts < GatewayCommand.max_attempts,
            )
        )
        for row in (await session.execute(q)).scalars().all():
            redis = RedisClient()
            try:
                await enqueue_command(
                    redis.client,
                    command_id=str(row.command_id),
                    gateway_mac=row.gateway.gateway_mac if row.gateway else "",
                    command_type=row.command_type,
                    payload=row.payload_json,
                )
            finally:
                await redis.client.aclose()
            row.attempts += 1
            row.next_retry_at = next_retry_datetime(row.attempts)
            retried += 1
        if retried:
            await session.commit()

        # sent past retry and at/over max attempts → failed
        q = (
            select(GatewayCommand)
            .options(selectinload(GatewayCommand.gateway))
            .where(
                GatewayCommand.status == "sent",
                GatewayCommand.next_retry_at.is_not(None),
                GatewayCommand.next_retry_at < now,
                GatewayCommand.attempts >= GatewayCommand.max_attempts,
            )
        )
        for row in (await session.execute(q)).scalars().all():
            row.status = "failed"
            row.error_message = "max attempts exhausted (retry timeout)"
            failed_sent += 1

        # pending stuck (never relayed) past TTL → failed
        q = (
            select(GatewayCommand)
            .where(
                GatewayCommand.status == "pending",
                GatewayCommand.created_at < pending_cutoff,
            )
        )
        for row in (await session.execute(q)).scalars().all():
            row.status = "failed"
            row.error_message = "expired before ingestion relay picked it up"
            failed_pending += 1

        await session.commit()

    return {"retried": retried, "failed_sent": failed_sent, "failed_pending": failed_pending}


@celery_app.task(name="commands.sweep_commands")
def sweep_commands() -> dict:
    return asyncio.run(_scan_and_sweep())