"""Integration test: authentication + role enforcement on read/mutation endpoints."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def users(db):
    """Seed one user per role; return {role: User}."""
    from fmp.core.database import async_session_factory
    from fmp.core.security import hash_password
    from fmp.models import User

    pw = hash_password("Passw0rd!")
    created = {}
    async with async_session_factory() as session:
        for idx, role in enumerate(("admin", "company_admin", "user")):
            user = User(
                username=f"{role}_{idx}", email=f"{role}_{idx}@t.io",
                password_hash=pw, role=role, is_active=True,
            )
            session.add(user)
            created[role] = user
        await session.commit()
    return created


@pytest_asyncio.fixture
async def tank_seed(db):
    from fmp.core.database import async_session_factory
    from fmp.models import Company, Site, Tank

    async with async_session_factory() as session:
        company = Company(name="SeedCo")
        session.add(company)
        await session.flush()
        site = Site(name="SeedSite", company_id=company.id)
        session.add(site)
        await session.flush()
        tank = Tank(
            name="SeedTank", site_id=site.id,
            sensor_serial_number=f"SN-SEED-{uuid.uuid4().hex[:6]}",
            tank_orientation="vertical", tank_diameter=2.0, tank_height=3.0,
            tank_volume=9200.0, calibration_factor=1.0,
        )
        session.add(tank)
        await session.commit()
        return tank.id


def _set_override(user):
    from fmp.api.main import app
    from fmp.api.deps import get_current_user

    app.dependency_overrides[get_current_user] = lambda: user


async def test_tanks_require_auth_and_roles(db, users, tank_seed):
    from fmp.api.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # unauthenticated reads are rejected
        app.dependency_overrides.clear()
        r = await client.get("/api/v1/tanks")
        assert r.status_code == 401

        # any authenticated user may read
        _set_override(users["user"])
        r = await client.get("/api/v1/tanks")
        assert r.status_code == 200

        # plain user cannot create a tank
        r = await client.post("/api/v1/tanks", json={
            "name": "Blocked", "sensor_serial_number": f"SN-{uuid.uuid4().hex[:8]}",
            "tank_orientation": "vertical", "tank_diameter": 2.0, "tank_height": 3.0,
            "tank_volume": 9200.0, "calibration_factor": 1.0,
        })
        assert r.status_code == 403

        # company_admin can create (company → site → tank)
        _set_override(users["company_admin"])
        r = await client.post("/api/v1/companies", json={"name": "Co T"})
        assert r.status_code == 201, r.text
        company_id = r.json()["id"]
        r = await client.post("/api/v1/sites", json={
            "name": "Site A", "company_id": company_id,
        })
        assert r.status_code == 201, r.text
        site_id = r.json()["id"]
        r = await client.post("/api/v1/tanks", json={
            "name": "Allowed", "site_id": site_id,
            "sensor_serial_number": f"SN-{uuid.uuid4().hex[:8]}",
            "tank_orientation": "vertical", "tank_diameter": 2.0, "tank_height": 3.0,
            "tank_volume": 9200.0, "calibration_factor": 1.0,
        })
        assert r.status_code == 201, r.text
        new_tank_id = r.json()["id"]

        # plain user cannot ack alarms even on a real tank
        _set_override(users["user"])
        r = await client.post(f"/api/v1/tanks/{tank_seed}/alarms/{uuid.uuid4()}/ack")
        assert r.status_code == 403

        # company_admin gets a proper 404 (authorized, alarm missing)
        _set_override(users["company_admin"])
        r = await client.post(f"/api/v1/tanks/{new_tank_id}/alarms/{uuid.uuid4()}/ack")
        assert r.status_code == 404


async def test_org_mutations_require_role(db, users):
    from fmp.api.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # plain user cannot create/destroy org entities
        _set_override(users["user"])
        r = await client.post("/api/v1/companies", json={"name": "Nope"})
        assert r.status_code == 403

        _set_override(users["company_admin"])
        r = await client.post("/api/v1/companies", json={"name": "Co A"})
        assert r.status_code == 201, r.text
        company_id = r.json()["id"]

        _set_override(users["user"])
        r = await client.delete(f"/api/v1/companies/{company_id}")
        assert r.status_code == 403

        # company_admin mutation still works after role guard
        _set_override(users["company_admin"])
        r = await client.patch(f"/api/v1/companies/{company_id}", json={"name": "Co B"})
        assert r.status_code == 200 and r.json()["name"] == "Co B"