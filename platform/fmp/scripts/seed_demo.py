"""Idempotent seed of demo operational data for local/staging environments.

Creates one demonstration hierarchy — a company, a site, a station with a
dispenser, an employee, two IoT gateways, two instrumented tanks — then backfills
~7 days of hourly telemetry (level/volume/pressure) with daily consumption and
periodic refills so the dashboard, analytics and consumption views have
realistic data to render.

Re-runnable: every object is upserted by its natural unique key
(company name, station/dispenser serial, gateway MAC, tank sensor serial) and
measurements insert with ON CONFLICT DO NOTHING. Safe to run against a fresh
dev DB after ``init_db``; never touches production data belonging to other
tenants.

Run:
    python -m fmp.scripts.seed_demo
"""
from __future__ import annotations

import asyncio
import math
import random
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

if TYPE_CHECKING:
    from fmp.models import Tank

COMPANY_NAME = "Demo Fuel Corp"
SITE_NAME = "Central Depot"
STATION_NAME = "Station 01"
STATION_SERIAL = "RPI-DEMO-0001"
DISPENSER_SERIAL = "DN-DEMO-0001"
EMPLOYEE_ID = "EMP-DEMO-0001"
GATEWAY_MACS = ["AA:BB:CC:10:00:01", "AA:BB:CC:10:00:02"]
SENSOR_SERIALS = ["SN-LVL-DEMO-0001", "SN-LVL-DEMO-0002"]
TANK_NAMES = ["Diesel Main", "Gasoline Main"]
FUEL_CODES = ["diesel", "gasoline"]
SEED_DAYS = 7
HOURS_PER_DAY = 24
TANK_VOLUME = 10000.0
TANK_HEIGHT = 3.0
TANK_DIAMETER = 2.0


def _level_volume(tank_volume: float, tank_height: float, fill_percent: float) -> tuple[float, float]:
    """Return (level_m, volume_liters) for a vertical cylinder at a fill %."""
    volume = tank_volume * fill_percent / 100.0
    level = volume / tank_volume * tank_height
    return round(level, 3), round(volume, 1)


def _pressure_bar(level_m: float, base_density_kgm3: float) -> float:
    """Hydrostatic pressure at the tank base (p = rho * g * h, in bar)."""
    return round(level_m * base_density_kgm3 * 9.81 / 1e5, 4)


def _hourly_volumes(days: int) -> list[float]:
    """Saw-tooth volume trace: ~4.5%/day consumption with refills every 2 days.

    Deterministic pseudo-random walk (fixed seed) so demo data is reproducible.
    """
    rng = random.Random(42)
    start = 8200.0
    volumes: list[float] = []
    v = start
    for i in range(days * HOURS_PER_DAY + 1):
        volumes.append(round(v, 1))
        hour_of_day = i % HOURS_PER_DAY
        if hour_of_day == 6 and 5 <= i // HOURS_PER_DAY % 2:
            v = start + rng.uniform(-700, -200)
        elif hour_of_day == 6:
            v = start + rng.uniform(300, 800)
        v -= rng.uniform(12.0, 30.0)  # hourly draw (L)
        v = max(v, 600.0)
    return volumes


async def _get_or_create(session: AsyncSession) -> dict:
    """Build the demo hierarchy; returns the created/updated object ids."""
    from fmp.models import (
        Company,
        Dispenser,
        Employee,
        FuelType,
        IoTGateway,
        Site,
        Station,
        Tank,
    )

    company = (
        await session.execute(select(Company).where(Company.name == COMPANY_NAME))
    ).scalar_one_or_none()
    if company is None:
        company = Company(
            name=COMPANY_NAME,
            address="1 Demo Road, Kigali",
            contact_name="Demo Operator",
            contact_email="demo@example.com",
            contact_phone="+250700000000",
        )
        session.add(company)
        await session.flush()

    site = (
        await session.execute(select(Site).where(Site.name == SITE_NAME))
    ).scalar_one_or_none()
    if site is None:
        site = Site(
            name=SITE_NAME,
            company_id=company.id,
            address="Depot Yard 1",
            location="-1.9509, 30.0705",
            is_active=True,
        )
        session.add(site)
        await session.flush()
    elif site.company_id != company.id:
        site.company_id = company.id

    station = (
        await session.execute(
            select(Station).where(Station.serial_number == STATION_SERIAL)
        )
    ).scalar_one_or_none()
    if station is None:
        station = Station(
            name=STATION_NAME,
            site_id=site.id,
            serial_number=STATION_SERIAL,
            raspberry_pi_id="pi-demo-0001",
            firmware_version="2.1.0",
            connection_status="online",
            last_heartbeat=datetime.now(timezone.utc),
        )
        session.add(station)
        await session.flush()
    else:
        station.site_id = site.id
        station.connection_status = "online"
        station.last_heartbeat = datetime.now(timezone.utc)

    dispenser = (
        await session.execute(
            select(Dispenser).where(Dispenser.serial_number == DISPENSER_SERIAL)
        )
    ).scalar_one_or_none()
    if dispenser is None:
        dispenser = Dispenser(
            name="Pump 1",
            station_id=station.id,
            serial_number=DISPENSER_SERIAL,
            modbus_address=1,
            dispenser_model="Gilbarco P500",
            is_active=True,
        )
        session.add(dispenser)
        await session.flush()
    else:
        dispenser.station_id = station.id

    employee = (
        await session.execute(select(Employee).where(Employee.employee_id == EMPLOYEE_ID))
    ).scalar_one_or_none()
    if employee is None:
        employee = Employee(
            employee_id=EMPLOYEE_ID,
            name="Demo Driver",
            phone="+250780000000",
            email="driver@example.com",
            company_id=company.id,
            is_active=True,
        )
        session.add(employee)
        await session.flush()

    fuel_types = {
        ft.code: ft
        for ft in (
            await session.execute(select(FuelType))
        ).scalars()
    }

    gateways: list[IoTGateway] = []
    for mac in GATEWAY_MACS:
        gw = (
            await session.execute(
                select(IoTGateway).where(IoTGateway.gateway_mac == mac)
            )
        ).scalar_one_or_none()
        if gw is None:
            gw = IoTGateway(
                gateway_mac=mac,
                name=f"Demo Gateway {mac[-2:]}",
                firmware_version="1.4.0",
                connection_status="online",
                is_active=True,
                last_seen=datetime.now(timezone.utc),
            )
            session.add(gw)
            await session.flush()
        else:
            gw.connection_status = "online"
            gw.last_seen = datetime.now(timezone.utc)
            gw.is_active = True
        gateways.append(gw)

    tanks: list[Tank] = []
    for idx, serial in enumerate(SENSOR_SERIALS):
        tank = (
            await session.execute(
                select(Tank).where(Tank.sensor_serial_number == serial)
            )
        ).scalar_one_or_none()
        fuel_code = FUEL_CODES[idx]
        fuel_type_id = fuel_types[fuel_code].id if fuel_code in fuel_types else None
        if tank is None:
            tank = Tank(
                name=TANK_NAMES[idx],
                site_id=site.id,
                gateway_id=gateways[idx].id,
                gateway_mac=gateways[idx].gateway_mac,
                sensor_serial_number=serial,
                device_address=idx + 1,
                tank_orientation="vertical",
                tank_height=TANK_HEIGHT,
                tank_diameter=TANK_DIAMETER,
                tank_volume=TANK_VOLUME,
                tank_shape="vertical_cylinder",
                fuel_type_id=fuel_type_id,
                elevation=0.0,
                calibration_factor=1.0,
                atmospheric_pressure=0.0,
                low_level_threshold=10.0,
                critical_level_threshold=5.0,
                high_level_threshold=95.0,
                low_volume_threshold=1000.0,
                high_volume_threshold=9500.0,
                is_active=True,
                connection_status="online",
                last_connection=datetime.now(timezone.utc),
            )
            session.add(tank)
            await session.flush()
        else:
            tank.site_id = site.id
            tank.gateway_id = gateways[idx].id
            tank.gateway_mac = gateways[idx].gateway_mac
            tank.connection_status = "online"
            tank.last_connection = datetime.now(timezone.utc)
        tanks.append(tank)

    return {
        "company": company.id,
        "site": site.id,
        "station": station.id,
        "dispenser": dispenser.id,
        "employee": employee.id,
        "gateways": [g.id for g in gateways],
        "tanks": [t.id for t in tanks],
        "fuel_types": list(fuel_types.keys()),
    }


def _build_measurement_rows(tank: Tank, fuel_density: float) -> list[dict]:
    volumes = _hourly_volumes(SEED_DAYS)
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=SEED_DAYS)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    rows: list[dict] = []
    for i, volume in enumerate(volumes):
        ts = start + timedelta(hours=i)
        fill_percent = round(volume / tank.tank_volume * 100.0, 2)
        # Gentle diurnal temperature curve so charts look organic.
        hour_of_day = i % HOURS_PER_DAY
        temp = round(
            25.0 - 4.0 * math.cos(2 * math.pi * hour_of_day / HOURS_PER_DAY), 1
        )
        level, _ = _level_volume(tank.tank_volume, tank.tank_height, fill_percent)
        rows.append(
            {
                "tank_id": tank.id,
                "timestamp": ts,
                "pressure": _pressure_bar(level, fuel_density),
                "temperature": temp,
                "level": level,
                "volume": volume,
                "flow_rate": 0.0,
                "gov_volume": round(volume * 0.985, 1),
                "net_volume": round(volume * 0.95, 1),
                "density_at_temperature": round(
                    fuel_density * (1 - 0.00080 * (temp - 15.0)), 2
                ),
                "fill_percent": fill_percent,
                "status": 0,
                "is_outlier": False,
            }
        )
    return rows


async def seed_demo(engine: AsyncEngine | None = None) -> dict:
    """Seed the demo hierarchy + telemetry; returns a summary of what exists."""
    from fmp.core.database import async_session_factory, engine as default_engine
    from fmp.models import FuelType, Tank
    from fmp.ingestion.batch_writer import ensure_hypertables, insert_measurements

    owns_engine = engine is None
    if owns_engine:
        engine = default_engine

    try:
        async with async_session_factory() as session:
            await ensure_hypertables(session)
            objects = await _get_or_create(session)

            fuel_density = {
                ft.code: ft.base_density
                for ft in (await session.execute(select(FuelType))).scalars()
            }

            tanks = (
                await session.execute(
                    select(Tank).where(
                        Tank.id.in_(objects["tanks"]),
                        Tank.deleted_at.is_(None),
                    )
                )
            ).scalars()

            inserted = 0
            for tank in tanks:
                code = (
                    await session.execute(
                        select(FuelType).where(FuelType.id == tank.fuel_type_id)
                    )
                ).scalar_one_or_none()
                density = (
                    fuel_density.get(code.code, 750.0) if code is not None else 750.0
                )
                rows = _build_measurement_rows(tank, density)
                inserted += await insert_measurements(session, rows)
            await session.commit()

        return {"inserted_measurements": inserted, **objects}
    finally:
        if owns_engine:
            await default_engine.dispose()


if __name__ == "__main__":
    result = asyncio.run(seed_demo())
    print(
        f"seeded demo: tanks={len(result['tanks'])} "
        f"measurements_inserted={result['inserted_measurements']}"
    )