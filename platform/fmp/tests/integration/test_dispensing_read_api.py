"""Integration test: read-only dispensing endpoints (allocations/transactions).

Seeds a Company → Employee → Allocation plus a DispenseTransaction via the ORM
(like test_dispense_flow.py) and verifies the read endpoints return the seeded
rows, not just 200 + empty lists.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def token_override(db):
    """Seed an admin user and override get_current_user to return it."""
    from fmp.api.main import app
    from fmp.api.deps import get_current_user
    from fmp.core.database import async_session_factory
    from fmp.core.security import hash_password
    from fmp.models import User

    pw = hash_password("AdminPass123")
    async with async_session_factory() as session:
        user = User(
            username=f"admin_{uuid.uuid4().hex[:6]}",
            email=f"admin_{uuid.uuid4().hex[:6]}@t.io",
            password_hash=pw, role="admin", is_active=True,
        )
        session.add(user)
        await session.commit()

    async def _override():
        return user

    app.dependency_overrides[get_current_user] = _override
    yield user
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client():
    from fmp.api.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def seed_data(db):
    """Seed Company → Employee → Allocation + DispenseTransaction rows."""
    from fmp.core.database import async_session_factory
    from fmp.models import (
        Allocation,
        Company,
        DispenseCode,
        DispenseTransaction,
        Dispenser,
        Employee,
        Site,
        Station,
        UploadBatch,
        User,
    )

    async with async_session_factory() as session:
        company = Company(name=f"ReadCo-{uuid.uuid4().hex[:6]}")
        session.add(company)
        await session.flush()

        site = Site(name="ReadSite", company_id=company.id)
        session.add(site)
        await session.flush()

        station = Station(name="ReadStation", site_id=site.id, serial_number=f"ST-{uuid.uuid4().hex[:8]}")
        session.add(station)
        await session.flush()

        dispenser = Dispenser(name="P1", station_id=station.id, serial_number=f"DN-{uuid.uuid4().hex[:8]}")
        session.add(dispenser)
        await session.flush()

        emp = Employee(
            employee_id=f"E-{uuid.uuid4().hex[:6]}", name="ReadTester",
            phone="700000001", company_id=company.id,
        )
        session.add(emp)
        await session.flush()

        admin = User(
            username=f"u{uuid.uuid4().hex[:6]}", email=f"{uuid.uuid4().hex[:6]}@t.io", password_hash="x"
        )
        session.add(admin)
        await session.flush()

        batch = UploadBatch(filename="read.csv", original_filename="read.csv", uploaded_by_id=admin.id, total_rows=1)
        session.add(batch)
        await session.flush()

        alloc = Allocation(
            employee_id=emp.id, upload_batch_id=batch.id, company_id=company.id,
            invoice_number="INV-READ", allocated_liters=100.0, dispensed_liters=0.0,
            remaining_liters=100.0, status="PENDING",
        )
        session.add(alloc)
        await session.flush()

        code = DispenseCode(
            allocation_id=alloc.id, code_hash=f"h{uuid.uuid4().hex}",
            code_fp=f"fp{uuid.uuid4().hex}", code_length=6,
            authorized_liters=100.0, consumed_liters=0.0, status="ACTIVE",
            max_attempts=5, expires_at=alloc.created_at,
        )
        session.add(code)
        await session.flush()

        session.add(DispenseTransaction(
            station_id=station.id, dispenser_id=dispenser.id, code_id=code.id,
            employee_id=emp.id, allocation_id=alloc.id,
            requested_liters=12.5, actual_liters=12.5,
            secret_totalizer_before=100, secret_totalizer_after=21250,
            status="COMPLETED",
        ))
        await session.commit()
        return {"dispenser_id": dispenser.id, "alloc_id": alloc.id}


async def test_allocation_and_transaction_reads(db, token_override, client, seed_data):
    r = await client.get("/api/v1/dispensing/allocations?max_rows=10")
    assert r.status_code == 200 and isinstance(r.json(), list)
    assert any(a["id"] == str(seed_data["alloc_id"]) for a in r.json())
    seeded = next(a for a in r.json() if a["id"] == str(seed_data["alloc_id"]))
    assert seeded["employee_name"] == "ReadTester"
    assert seeded["allocated_liters"] == 100.0
    assert seeded["status"] == "PENDING"

    r = await client.get(f"/api/v1/dispensing/transactions?dispenser_id={seed_data['dispenser_id']}")
    assert r.status_code == 200 and isinstance(r.json(), list)
    assert any(t["requested_liters"] == 12.5 for t in r.json())
    assert any(t["actual_liters"] == 12.5 for t in r.json())

    r = await client.get("/api/v1/dispensing/transactions?limit=5")
    assert r.status_code == 200


async def test_read_endpoints_empty_list(db, token_override, client):
    """GET /allocations + /transactions on a fresh DB (no seed) return 200 + []."""
    r = await client.get("/api/v1/dispensing/allocations?max_rows=10")
    assert r.status_code == 200
    assert r.json() == []

    r = await client.get("/api/v1/dispensing/transactions?limit=10")
    assert r.status_code == 200
    assert r.json() == []


async def test_read_endpoints_reject_negative_params(db, token_override, client):
    """Negative max_rows/limit must be rejected with 422, not hit the DB (500)."""
    r = await client.get("/api/v1/dispensing/allocations?max_rows=-5")
    assert r.status_code == 422

    r = await client.get("/api/v1/dispensing/transactions?limit=-5")
    assert r.status_code == 422
