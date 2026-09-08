"""Integration test: fuel-types + strapping-table endpoints."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def token_override(db):
    """Seed an admin user and override get_current_user."""
    from fmp.api.main import app
    from fmp.api.deps import get_current_user
    from fmp.core.database import async_session_factory
    from fmp.core.security import hash_password
    from fmp.models import User

    pw = hash_password("AdminPass123")
    async with async_session_factory() as session:
        admin = User(
            username=f"root_{uuid.uuid4().hex[:6]}",
            email=f"root_{uuid.uuid4().hex[:6]}@t.io",
            password_hash=pw, role="admin", is_active=True,
        )
        session.add(admin)
        await session.commit()

    async def _override():
        return admin

    app.dependency_overrides[get_current_user] = _override
    yield admin
    app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture
async def tank_seed(db, token_override):
    """Seed Company → Site → Tank (with a fuel type)."""
    from fmp.core.database import async_session_factory
    from fmp.models import Company, FuelType, Site, Tank

    async with async_session_factory() as session:
        company = Company(name="SeedCo")
        session.add(company)
        await session.flush()
        site = Site(name="SeedSite", company_id=company.id)
        session.add(site)
        await session.flush()
        fuel = FuelType(
            code="diesel", name="Diesel", base_density=845.0,
            thermal_expansion_coeff=0.0008, max_vapor_pressure=2.0,
            viscosity_cst=2.5,
        )
        session.add(fuel)
        await session.flush()
        tank = Tank(
            name="SeedTank", site_id=site.id,
            fuel_type_id=fuel.id,
            sensor_serial_number=f"SN-FUEL-{uuid.uuid4().hex[:6]}",
            tank_orientation="vertical", tank_diameter=2.0, tank_height=3.0,
            tank_volume=9200.0, calibration_factor=1.0,
        )
        session.add(tank)
        await session.commit()
        return tank


@pytest_asyncio.fixture
async def client():
    from fmp.api.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_fuel_types_list_and_create_roles(db, token_override, client):
    r = await client.get("/api/v1/fuel-types")
    assert r.status_code == 200
    # bad payload rejected
    r = await client.post("/api/v1/fuel-types", json={"code": "bad density!"})
    assert r.status_code == 422
    # admin can create
    r = await client.post("/api/v1/fuel-types", json={
        "code": "test_fuel", "name": "Test", "base_density": 700.0,
        "thermal_expansion_coeff": 0.0009, "max_vapor_pressure": 3.0, "viscosity_cst": 1.0,
    })
    assert r.status_code == 201, r.text
    assert r.json()["base_density"] == 700.0


async def test_strapping_upsert_and_read(db, token_override, client, tank_seed):
    r = await client.put(f"/api/v1/tanks/{tank_seed.id}/strapping", json={
        "calibration_data": [{"height": 0.0, "volume": 0.0},
                             {"height": 1.0, "volume": 700.0},
                             {"height": 2.0, "volume": 1500.0}],
        "interpolation_method": "cubic_spline",
    })
    assert r.status_code == 200, r.text
    assert r.json()["interpolation_method"] == "cubic_spline"
    got = await client.get(f"/api/v1/tanks/{tank_seed.id}/strapping")
    assert got.status_code == 200 and len(got.json()["calibration_data"]) == 3
    # tank now points at the table
    tank = await client.get(f"/api/v1/tanks/{tank_seed.id}")
    assert tank.json()["strapping_table_id"] == r.json()["id"]


async def test_strapping_missing_returns_404(db, token_override, client, tank_seed):
    r = await client.get(f"/api/v1/tanks/{tank_seed.id}/strapping")
    assert r.status_code == 404
