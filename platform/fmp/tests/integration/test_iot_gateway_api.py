"""Integration test: IoT gateway CRUD API (create/list/get/patch/link)."""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def api(db):
    from fmp.api.deps import get_current_user
    from fmp.api.main import app
    from fmp.core.database import async_session_factory
    from fmp.core.security import hash_password
    from fmp.models import Company, Site, Tank, User

    async with async_session_factory() as session:
        admin = User(
            username="gw_admin", email="gw@t.io",
            password_hash=hash_password("AdminPass123"),
            role="admin", is_active=True,
        )
        session.add(admin)

        company = Company(name="TestCo")
        session.add(company)
        await session.flush()

        site = Site(name="TestSite", company_id=company.id)
        session.add(site)
        await session.flush()

        tank = Tank(
            name="SeedTank", site_id=site.id,
            sensor_serial_number="SN-GW-T01",
            tank_orientation="vertical", tank_diameter=2.0, tank_height=3.0,
            tank_volume=9200.0, calibration_factor=1.0,
        )
        session.add(tank)
        await session.commit()

    async def _override():
        return admin

    app.dependency_overrides[get_current_user] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def test_gateway_crud_and_link(api):
    r = await api.post("/api/v1/iot-gateways", json={
        "gateway_mac": "AA:BB:CC:DD:EE:01", "name": "East Gate",
        "firmware_version": "2.1.0",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    gw_id = body["id"]
    assert body["gateway_mac"] == "AA:BB:CC:DD:EE:01"
    assert body["name"] == "East Gate"
    assert body["is_active"] is False
    assert body["connection_status"] == "offline"
    assert body["tank_ids"] == []

    # duplicate MAC → 409
    r = await api.post("/api/v1/iot-gateways", json={"gateway_mac": "AA:BB:CC:DD:EE:01"})
    assert r.status_code == 409

    # list
    r = await api.get("/api/v1/iot-gateways")
    assert r.status_code == 200 and len(r.json()) == 1

    # get single
    r = await api.get(f"/api/v1/iot-gateways/{gw_id}")
    assert r.status_code == 200 and r.json()["name"] == "East Gate"

    # patch: rename + link a tank (the api fixture seeds one)
    from fmp.core.database import async_session_factory
    from fmp.models import Tank
    from sqlalchemy import select

    async with async_session_factory() as session:
        tank = (await session.execute(select(Tank))).scalars().first()
        assert tank is not None
        tank_id = str(tank.id)

    r = await api.patch(f"/api/v1/iot-gateways/{gw_id}", json={
        "name": "East Gate II", "is_active": True,
    })
    assert r.status_code == 200
    assert r.json()["name"] == "East Gate II" and r.json()["is_active"] is True

    # link tank (first link → is_active True)
    r = await api.patch(f"/api/v1/iot-gateways/{gw_id}", json={"tank_ids": [tank_id]})
    assert r.status_code == 200
    assert r.json()["tank_ids"] == [tank_id]
    assert r.json()["is_active"] is True
    async with async_session_factory() as session:
        t = await session.get(Tank, tank_id)
        assert str(t.gateway_id) == gw_id

    # unlink (replace with empty list); is_active stays True
    r = await api.patch(f"/api/v1/iot-gateways/{gw_id}", json={"tank_ids": []})
    assert r.status_code == 200
    assert r.json()["tank_ids"] == []
    assert r.json()["is_active"] is True
    async with async_session_factory() as session:
        t = await session.get(Tank, tank_id)
        assert t.gateway_id is None

    # get missing → 404
    import uuid
    r = await api.get(f"/api/v1/iot-gateways/{uuid.uuid4()}")
    assert r.status_code == 404


async def test_gateway_admin_only_write(api):
    # a plain "user"-role account cannot create a gateway (403 via role guard)
    from fmp.api.deps import get_current_user
    from fmp.api.main import app
    from fmp.core.database import async_session_factory
    from fmp.core.security import hash_password
    from fmp.models import User

    async with async_session_factory() as session:
        user = User(
            username="plain", email="p@t.io",
            password_hash=hash_password("TestPass123"),
            role="user", is_active=True,
        )
        session.add(user)
        await session.commit()

    app.dependency_overrides[get_current_user] = lambda: user
    r = await api.post("/api/v1/iot-gateways", json={"gateway_mac": "AA:BB:CC:DD:EE:09"})
    assert r.status_code == 403, r.text


async def test_company_admin_cannot_send(api):
    from fmp.api.deps import get_current_user
    from fmp.api.main import app
    from fmp.core.database import async_session_factory
    from fmp.core.security import hash_password
    from fmp.models import User

    async with async_session_factory() as session:
        ca = User(
            username="comp_admin", email="ca@t.io",
            password_hash=hash_password("TestPass123"),
            role="company_admin", is_active=True,
        )
        session.add(ca)
        await session.commit()

    app.dependency_overrides[get_current_user] = lambda: ca
    r = await api.post("/api/v1/iot-gateways", json={"gateway_mac": "AA:BB:CC:DD:EE:10"})
    assert r.status_code == 403, r.text


async def test_issue_command_and_history(api):
    from fmp.core.redis import RedisClient
    from fmp.ingestion.relay import QUEUE_OUTBOUND

    r = await api.post("/api/v1/iot-gateways", json={"gateway_mac": "AA:BB:CC:DD:EE:02"})
    gw_id = r.json()["id"]

    # activate so the command path is exercised (409 → 202)
    r = await api.patch(f"/api/v1/iot-gateways/{gw_id}", json={"is_active": True})
    assert r.status_code == 200, r.text

    r = await api.post(f"/api/v1/iot-gateways/{gw_id}/commands", json={
        "command_type": "set_interval", "payload": {"interval_s": 5},
    })
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "pending"
    command_id = body["command_id"]

    # frame is on the durable outbound queue
    redis = RedisClient()
    await redis.client.delete(QUEUE_OUTBOUND)
    # re-issue so this test is hermetic
    r = await api.post(f"/api/v1/iot-gateways/{gw_id}/commands", json={
        "command_type": "status_probe", "payload": {},
    })
    assert r.status_code == 202
    second_id = r.json()["command_id"]
    n = await redis.client.llen(QUEUE_OUTBOUND)
    assert n >= 1
    await redis.client.delete(QUEUE_OUTBOUND)
    await redis.client.aclose()

    # history lists both
    r = await api.get(f"/api/v1/iot-gateways/{gw_id}/commands")
    assert r.status_code == 200
    ids = [c["command_id"] for c in r.json()]
    assert command_id in ids and second_id in ids
    assert all(c["status"] == "pending" for c in r.json())

    # invalid payload → 422
    r = await api.post(f"/api/v1/iot-gateways/{gw_id}/commands", json={
        "command_type": "set_interval", "payload": {"interval_s": 0},
    })
    assert r.status_code == 422

    # unknown gateway → 404
    import uuid
    r = await api.post(f"/api/v1/iot-gateways/{uuid.uuid4()}/commands", json={
        "command_type": "reboot", "payload": {},
    })
    assert r.status_code == 404
