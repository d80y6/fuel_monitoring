"""Fuel type CRUD (audit G-105).

Fuel types are the platform-wide product catalogue. The two behaviours worth
pinning are that a type still referenced by tanks cannot be deleted — those
tanks carry volumes computed with that product's density, so removing it would
leave uninterpretable history — and that every mutation is audited.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from fmp.api.main import app
from fmp.core.database import async_session_factory
from fmp.core.security import hash_password
from fmp.models import AuditEvent, Company, FuelType, Site, Tank, User

pytestmark = pytest.mark.asyncio

NEW_TYPE = {
    "code": "test_lpg",
    "name": "Test LPG",
    "base_density": 530.0,
    "thermal_expansion_coeff": 0.0025,
    "max_vapor_pressure": 8.5,
    "viscosity_cst": 0.12,
}


@pytest_asyncio.fixture
async def admin(client_seed):
    return client_seed


@pytest_asyncio.fixture
async def client_seed(db):
    """An authenticated client acting as a platform admin."""
    async with async_session_factory() as session:
        root = User(
            username="ft_root",
            email="ft_root@example.test",
            password_hash=hash_password("RootPass123!"),
            role="admin",
            company_id=None,
        )
        session.add(root)
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/auth/login", json={"username": "ft_root", "password": "RootPass123!"}
        )
        assert resp.status_code == 200, resp.text
        c.headers["Authorization"] = f"Bearer {resp.json()['access_token']}"
        yield c


async def test_list_is_available_to_any_authenticated_user(client_seed):
    resp = await client_seed.get("/api/v1/fuel-types")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_create_persists_and_audits(client_seed):
    resp = await client_seed.post("/api/v1/fuel-types", json=NEW_TYPE)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["code"] == "test_lpg"
    assert body["base_density"] == pytest.approx(530.0)

    async with async_session_factory() as session:
        row = (
            await session.execute(FuelType.__table__.select().where(FuelType.code == "test_lpg"))
        ).first()
        assert row is not None, "the fuel type must be persisted, not just echoed"
        event = (
            await session.execute(
                AuditEvent.__table__.select().where(AuditEvent.action == "fuel_type.create")
            )
        ).first()
        assert event is not None, "creating a product must leave an audit trail"


async def test_duplicate_code_is_rejected(client_seed):
    await client_seed.post("/api/v1/fuel-types", json=NEW_TYPE)
    resp = await client_seed.post("/api/v1/fuel-types", json=NEW_TYPE)
    assert resp.status_code == 409, resp.text


async def test_update_changes_only_the_supplied_fields(client_seed):
    created = (await client_seed.post("/api/v1/fuel-types", json=NEW_TYPE)).json()
    resp = await client_seed.patch(
        f"/api/v1/fuel-types/{created['code']}", json={"base_density": 540.0}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["base_density"] == pytest.approx(540.0)
    assert body["name"] == NEW_TYPE["name"], "unsupplied fields must be preserved"
    assert body["code"] == "test_lpg", "code is immutable"


async def test_update_unknown_code_is_404(client_seed):
    resp = await client_seed.patch("/api/v1/fuel-types/nope", json={"base_density": 1.0})
    assert resp.status_code == 404, resp.text


async def test_delete_removes_an_unused_type(client_seed):
    created = (await client_seed.post("/api/v1/fuel-types", json=NEW_TYPE)).json()
    resp = await client_seed.delete(f"/api/v1/fuel-types/{created['code']}")
    assert resp.status_code == 204, resp.text

    async with async_session_factory() as session:
        row = (
            await session.execute(
                FuelType.__table__.select().where(FuelType.code == "test_lpg")
            )
        ).first()
        assert row is None


async def test_delete_is_refused_while_a_tank_references_the_type(client_seed):
    """History would become uninterpretable: those volumes used this density."""
    created = (await client_seed.post("/api/v1/fuel-types", json=NEW_TYPE)).json()
    fuel_id = uuid.UUID(created["id"])

    async with async_session_factory() as session:
        company = Company(name="ft-corp")
        session.add(company)
        await session.flush()
        site = Site(name="ft-site", company_id=company.id)
        session.add(site)
        await session.flush()
        session.add(
            Tank(
                name="ft-tank",
                site_id=site.id,
                sensor_serial_number="FT-TANK-1",
                tank_diameter=2.0,
                tank_volume=12000.0,
                fuel_type_id=fuel_id,
            )
        )
        await session.commit()

    resp = await client_seed.delete(f"/api/v1/fuel-types/{created['code']}")
    assert resp.status_code == 409, resp.text
    assert "reassign" in resp.text.lower()

    async with async_session_factory() as session:
        row = (
            await session.execute(
                FuelType.__table__.select().where(FuelType.code == "test_lpg")
            )
        ).first()
        assert row is not None, "a refused delete must not remove the row"


async def test_anonymous_cannot_mutate_the_catalogue(db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.post("/api/v1/fuel-types", json=NEW_TYPE)).status_code in (401, 403)
        assert (await c.patch("/api/v1/fuel-types/gasoline", json={})).status_code in (401, 403)
        assert (await c.delete("/api/v1/fuel-types/gasoline")).status_code in (401, 403)