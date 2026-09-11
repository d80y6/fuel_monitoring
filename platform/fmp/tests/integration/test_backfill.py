"""Integration test: tanks.gateway_id backfill from gateway_mac."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_backfill_assigns_gateway_id(requires_infra, db):
    from fmp.core.database import async_session_factory
    from fmp.models import Company, IoTGateway, Site, Tank
    from fmp.scripts.backfill_gateways import backfill_gateways
    from sqlalchemy import select

    async with async_session_factory() as session:
        company = Company(name="BackfillCo")
        session.add(company)
        await session.flush()
        site = Site(name="BackfillSite", company_id=company.id)
        session.add(site)
        await session.flush()

        sn = "SN-BACKFILL-1"
        tank = Tank(
            name="Gen A", site_id=site.id, sensor_serial_number=sn,
            gateway_mac="AA:BB:CC:DD:EE:88",
            tank_orientation="vertical", tank_diameter=2.0, tank_height=3.0,
            tank_volume=9200.0, elevation=0.0, calibration_factor=1.0,
            fuel_type=None, critical_level_threshold=0.5, low_level_threshold=1.0,
            high_level_threshold=2.8, low_volume_threshold=2000.0,
        )
        session.add(tank)
        await session.commit()

    await backfill_gateways()

    async with async_session_factory() as session:
        tank = (await session.execute(
            select(Tank).where(Tank.sensor_serial_number == sn)
        )).scalar_one()
        assert tank.gateway_id is not None
        gw = (await session.execute(
            select(IoTGateway).where(IoTGateway.gateway_mac == "AA:BB:CC:DD:EE:88")
        )).scalar_one()
        assert gw.id == tank.gateway_id
        assert gw.is_active is True


async def test_backfill_idempotent(requires_infra, db):
    from fmp.core.database import async_session_factory
    from fmp.models import Company, IoTGateway, Site, Tank
    from fmp.scripts.backfill_gateways import backfill_gateways
    from sqlalchemy import select, func

    async with async_session_factory() as session:
        co = Company(name="TestCo-Idem")
        session.add(co)
        await session.flush()
        site = Site(name="Idem Site", company_id=co.id)
        session.add(site)
        await session.flush()
        sn = "SN-IDEM-1"
        tank = Tank(
            name="Idem Tank", site_id=site.id, sensor_serial_number=sn,
            gateway_mac="AA:BB:CC:DD:EE:99",
            tank_orientation="vertical", tank_diameter=2.0, tank_height=3.0,
            tank_volume=9200.0, elevation=0.0, calibration_factor=1.0,
            fuel_type=None, critical_level_threshold=0.5, low_level_threshold=1.0,
            high_level_threshold=2.8, low_volume_threshold=2000.0,
        )
        session.add(tank)
        await session.commit()

    await backfill_gateways()
    await backfill_gateways()  # run twice — must be idempotent

    async with async_session_factory() as session:
        gw_count = (await session.execute(
            select(func.count()).select_from(IoTGateway).where(IoTGateway.gateway_mac == "AA:BB:CC:DD:EE:99")
        )).scalar()
        assert gw_count == 1
        tank = (await session.execute(
            select(Tank).where(Tank.sensor_serial_number == sn)
        )).scalar_one()
        assert tank.gateway_id is not None