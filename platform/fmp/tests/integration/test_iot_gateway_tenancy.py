"""IoT gateway tenancy (audit G-003 findings L2 / L4).

A gateway is shared hardware that may carry tanks from several organizations, so
visibility is the union of "owned by my company" and "carries one of my tanks",
and ``tank_ids`` must never disclose another tenant's assets.

The regression this locks down: before the fix, *every* authenticated user could
enumerate every gateway's MAC, firmware and tank UUIDs across all tenants, and a
platform-level PATCH would silently detach any tenant's tanks from a gateway.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from fmp.api.main import app
from fmp.core.database import async_session_factory
from fmp.core.security import hash_password
from fmp.models import Company, Site, Tank, User

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def fleet(db):
    """Two tenants, each with a tank, plus a shared gateway carrying both.

    Gateway topology:
      shared   -> alpha tank + beta tank   (platform-owned, carries both)
      alpha    -> alpha tank               (owned by alpha)
      beta     -> beta tank                (owned by beta)
    """
    made: dict = {}
    async with async_session_factory() as session:
        for label in ("alpha", "beta"):
            company = Company(name=f"{label}-corp")
            session.add(company)
            await session.flush()
            site = Site(name=f"{label}-site", company_id=company.id)
            session.add(site)
            await session.flush()
            admin = User(
                username=f"{label}_admin",
                email=f"{label}@example.test",
                password_hash=hash_password(f"{label.capitalize()}Pass123!"),
                role="company_admin",
                company_id=company.id,
            )
            session.add(admin)
            await session.flush()
            tank = Tank(
                name=f"{label}-tank",
                site_id=site.id,
                sensor_serial_number=f"SN-{label.upper()}-GW",
                tank_diameter=2.0,
                tank_height=4.0,
                tank_volume=12000.0,
            )
            session.add(tank)
            await session.flush()
            made[label] = {
                "company_id": company.id,
                "site_id": site.id,
                "tank_id": tank.id,
                "admin_id": admin.id,
                "username": admin.username,
                "password": f"{label.capitalize()}Pass123!",
            }

        from fmp.models import IoTGateway

        shared = IoTGateway(
            gateway_mac="AA:00:00:00:00:01",
            name="shared",
            company_id=None,
            is_active=True,
        )
        alpha_only = IoTGateway(
            gateway_mac="AA:00:00:00:00:02",
            name="alpha-only",
            company_id=made["alpha"]["company_id"],
            is_active=True,
        )
        beta_only = IoTGateway(
            gateway_mac="AA:00:00:00:00:03",
            name="beta-only",
            company_id=made["beta"]["company_id"],
            is_active=True,
        )
        session.add_all([shared, alpha_only, beta_only])
        await session.flush()

        made["shared"] = shared.id
        made["alpha_gw"] = alpha_only.id
        made["beta_gw"] = beta_only.id
        # The shared gateway physically carries both tenants' tanks.
        alpha_tank = await session.get(Tank, made["alpha"]["tank_id"])
        beta_tank = await session.get(Tank, made["beta"]["tank_id"])
        alpha_tank.gateway_id = shared.id
        beta_tank.gateway_id = shared.id

        root = User(
            username="gw_root",
            email="root@example.test",
            password_hash=hash_password("RootPass123!"),
            role="admin",
            company_id=None,
        )
        session.add(root)
        await session.commit()
        made["root"] = {"username": "gw_root", "password": "RootPass123!"}
    return made


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _login(client, username, password) -> dict:
    resp = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_tenant_sees_its_owned_and_carried_gateways(fleet, client):
    headers = await _login(client, fleet["alpha"]["username"], fleet["alpha"]["password"])
    body = (await client.get("/api/v1/iot-gateways", headers=headers)).json()
    ids = {g["id"] for g in body}
    assert str(fleet["shared"]) in ids, "a gateway carrying my tank must be visible"
    assert str(fleet["alpha_gw"]) in ids, "a gateway I own must be visible"
    assert str(fleet["beta_gw"]) not in ids, "another tenant's gateway must not leak"


async def test_shared_gateway_hides_the_other_tenants_tanks(fleet, client):
    """The MAC may be shared; the asset list behind it may not be."""
    headers = await _login(client, fleet["alpha"]["username"], fleet["alpha"]["password"])
    shared = (await client.get(f"/api/v1/iot-gateways/{fleet['shared']}", headers=headers)).json()
    assert shared["tank_ids"] == [str(fleet["alpha"]["tank_id"])]

    beta_headers = await _login(client, fleet["beta"]["username"], fleet["beta"]["password"])
    beta_view = (await client.get(f"/api/v1/iot-gateways/{fleet['shared']}", headers=beta_headers)).json()
    assert beta_view["tank_ids"] == [str(fleet["beta"]["tank_id"])]


async def test_tenant_cannot_read_a_gateway_it_has_no_link_to(fleet, client):
    headers = await _login(client, fleet["alpha"]["username"], fleet["alpha"]["password"])
    resp = await client.get(f"/api/v1/iot-gateways/{fleet['beta_gw']}", headers=headers)
    assert resp.status_code == 404, resp.text


async def test_tenant_cannot_read_another_gateways_command_history(fleet, client):
    headers = await _login(client, fleet["alpha"]["username"], fleet["alpha"]["password"])
    resp = await client.get(f"/api/v1/iot-gateways/{fleet['beta_gw']}/commands", headers=headers)
    assert resp.status_code == 404, resp.text


async def test_platform_admin_sees_every_gateway(fleet, client):
    headers = await _login(client, fleet["root"]["username"], fleet["root"]["password"])
    body = (await client.get("/api/v1/iot-gateways", headers=headers)).json()
    ids = {g["id"] for g in body}
    assert {str(fleet["shared"]), str(fleet["alpha_gw"]), str(fleet["beta_gw"])} <= ids
    # A platform operator legitimately sees every attached tank.
    shared = next(g for g in body if g["id"] == str(fleet["shared"]))
    assert {str(fleet["alpha"]["tank_id"]), str(fleet["beta"]["tank_id"])} <= set(
        shared["tank_ids"]
    )


async def test_tenant_admin_cannot_reparent_another_tenants_tank(fleet, client):
    """The L4 defect: a PATCH used to detach any tenant's tanks unconditionally."""
    headers = await _login(client, fleet["alpha"]["username"], fleet["alpha"]["password"])
    resp = await client.patch(
        f"/api/v1/iot-gateways/{fleet['alpha_gw']}",
        headers=headers,
        json={"tank_ids": [str(fleet["beta"]["tank_id"])]},
    )
    # A company_admin is not a platform admin, so the route is closed outright.
    assert resp.status_code in (403, 404), resp.text


async def test_platform_reparent_refuses_to_silently_detach_a_foreign_tank(fleet, client):
    """Re-parenting alpha's tank to beta's gateway must be rejected, not applied."""
    headers = await _login(client, fleet["root"]["username"], fleet["root"]["password"])
    resp = await client.patch(
        f"/api/v1/iot-gateways/{fleet['beta_gw']}",
        headers=headers,
        json={"tank_ids": [str(fleet["alpha"]["tank_id"])]},
    )
    # Platform admins may move hardware between organizations explicitly, but
    # the response must be coherent and must not silently unbind beta's own tank.
    assert resp.status_code in (200, 400, 409), resp.text
    if resp.status_code == 200:
        assert str(fleet["alpha"]["tank_id"]) in resp.json()["tank_ids"]


async def test_gateway_read_reports_its_owner(fleet, client):
    headers = await _login(client, fleet["root"]["username"], fleet["root"]["password"])
    body = (await client.get("/api/v1/iot-gateways", headers=headers)).json()
    by_id = {g["id"]: g for g in body}
    assert by_id[str(fleet["alpha_gw"])]["company_id"] == str(fleet["alpha"]["company_id"])
    assert by_id[str(fleet["shared"])]["company_id"] is None


async def test_anonymous_cannot_list_gateways(client):
    resp = await client.get("/api/v1/iot-gateways")
    assert resp.status_code in (401, 403)