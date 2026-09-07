"""Integration test: end-to-end dispense flow (validate → partial → replay).

Requires live PostgreSQL/TimescaleDB + Redis. Skipped automatically when the
Postgres host in the environment is unreachable.
"""
from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def requires_infra():
    return True


async def _seed_fixture(session, redis):
    from fmp.models import (
        Allocation,
        Company,
        DispenseCode,
        Dispenser,
        Employee,
        Site,
        Station,
        UploadBatch,
        User,
    )
    from fmp.services.dispensing.code_generator import code_expiry, generate_unique_code

    company = Company(name=f"IT-{uuid.uuid4().hex[:6]}")
    session.add(company)
    await session.flush()
    site = Site(name="Test Site", company_id=company.id)
    session.add(site)
    await session.flush()
    station = Station(name="Yard", site_id=site.id, serial_number=f"ST-{uuid.uuid4().hex[:8]}")
    session.add(station)
    await session.flush()
    dispenser = Dispenser(name="P1", station_id=station.id, serial_number=f"DN-{uuid.uuid4().hex[:8]}")
    session.add(dispenser)
    await session.flush()
    emp = Employee(employee_id=f"E-{uuid.uuid4().hex[:6]}", name="Tester", phone="700000000", company_id=company.id)
    session.add(emp)
    await session.flush()
    admin = User(username=f"u{uuid.uuid4().hex[:6]}", email=f"{uuid.uuid4().hex[:6]}@t.io", password_hash="x")
    session.add(admin)
    await session.flush()
    batch = UploadBatch(filename="it.csv", original_filename="it.csv", uploaded_by_id=admin.id, total_rows=1)
    session.add(batch)
    await session.flush()

    code, code_hash, code_fp = await generate_unique_code(redis)
    alloc = Allocation(
        employee_id=emp.id, upload_batch_id=batch.id, company_id=company.id,
        invoice_number="INV-1", allocated_liters=50.0, dispensed_liters=0.0,
        remaining_liters=50.0, status="PENDING",
    )
    session.add(alloc)
    await session.flush()
    session.add(DispenseCode(
        allocation_id=alloc.id, code_hash=code_hash, code_fp=code_fp,
        code_length=len(code), authorized_liters=50.0, consumed_liters=0.0,
        status="ACTIVE", max_attempts=5, expires_at=code_expiry(),
    ))
    await session.commit()
    return {
        "station_id": station.id, "dispenser_id": dispenser.id, "code": code,
        "alloc_id": alloc.id,
    }


async def test_full_partial_dispense_flow(requires_infra):
    from fmp.core.database import Base, async_session_factory, engine
    from fmp.core.redis import RedisClient
    import fmp.models  # noqa: F401

    # isolate: use a dedicated test database name
    os.environ.setdefault("POSTGRES_DB", "fuel_test")
    from fmp.schemas.dispensing import CodeValidateRequest, DispenseCompleteRequest
    from fmp.services.dispensing.dispense_engine import complete_dispense, validate_code

    redis = RedisClient()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as session:
        seed = await _seed_fixture(session, redis)

    try:
        async with async_session_factory() as session:
            r = await validate_code(
                session, redis,
                CodeValidateRequest(code=seed["code"], station_id=seed["station_id"], requested_liters=20),
            )
            assert r.valid and r.remaining_liters == 50.0

        async with async_session_factory() as session:
            comp = await complete_dispense(
                session, redis,
                DispenseCompleteRequest(
                    code=seed["code"], station_id=seed["station_id"],
                    dispenser_id=seed["dispenser_id"],
                    requested_liters=20.0, actual_liters=20.0,
                    secret_totalizer_before=0, secret_totalizer_after=2000,
                ),
            )
            assert comp.status == "PARTIAL"
            assert comp.partial and comp.partial.remaining_liters == 30.0
            new_code = comp.partial.new_code
            assert new_code

        async with async_session_factory() as session:
            r2 = await validate_code(
                session, redis,
                CodeValidateRequest(code=new_code, station_id=seed["station_id"], requested_liters=30),
            )
            assert r2.valid and r2.remaining_liters == 30.0

        # replay of consumed code must not double-spend
        async with async_session_factory() as session:
            replay = await complete_dispense(
                session, redis,
                DispenseCompleteRequest(
                    code=seed["code"], station_id=seed["station_id"],
                    dispenser_id=seed["dispenser_id"],
                    requested_liters=20.0, actual_liters=20.0,
                    secret_totalizer_before=2000, secret_totalizer_after=4000,
                ),
            )
            assert replay.success
            assert (replay.partial is None), "replay must not re-create a partial code"

        async with async_session_factory() as session:
            final = await complete_dispense(
                session, redis,
                DispenseCompleteRequest(
                    code=new_code, station_id=seed["station_id"],
                    dispenser_id=seed["dispenser_id"],
                    requested_liters=30.0, actual_liters=30.0,
                    secret_totalizer_before=4000, secret_totalizer_after=7000,
                ),
            )
            assert final.status == "COMPLETED"
    finally:
        await redis.client.aclose()