"""One-shot gateway backfill: add tanks.gateway_id and map legacy gateway_mac.

Runs as part of the compose db-init step. Idempotent:
  ALTER TABLE ... ADD COLUMN IF NOT EXISTS; upsert iot_gateways from distinct
  tank.gateway_mac; set tanks.gateway_id.
"""
from __future__ import annotations

import asyncio

from sqlalchemy import text


async def _run() -> None:
    from fmp.core.database import engine

    async with engine.begin() as conn:
        await conn.execute(text(
            "ALTER TABLE tanks ADD COLUMN IF NOT EXISTS gateway_id UUID "
            "REFERENCES iot_gateways(id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_tanks_gateway_id ON tanks (gateway_id)"
        ))
        await conn.execute(text(
            "INSERT INTO iot_gateways (id, gateway_mac, name, is_active, connection_status, created_at, updated_at) "
            "SELECT gen_random_uuid(), t.gateway_mac, t.gateway_mac, TRUE, 'offline', now(), now() "
            "FROM (SELECT DISTINCT gateway_mac FROM tanks "
            "      WHERE gateway_mac IS NOT NULL AND gateway_mac <> '') t "
            "ON CONFLICT (gateway_mac) DO NOTHING"
        ))
        await conn.execute(text(
            "UPDATE tanks SET gateway_id = gw.id "
            "FROM iot_gateways gw WHERE gw.gateway_mac = tanks.gateway_mac "
            "AND tanks.gateway_id IS NULL"
        ))
    await engine.dispose()


async def backfill_gateways() -> None:
    await _run()


if __name__ == "__main__":
    asyncio.run(backfill_gateways())