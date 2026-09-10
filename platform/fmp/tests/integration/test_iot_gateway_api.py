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
    from fmp.models import User

    async with async_session_factory() as session:
        admin = User(
            username="gw_admin", email="gw@t.io",
            password_hash=hash_password("AdminPass123"),
            role="admin", is_active=True,
        )
        session.add(admin)
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

    # patch: rename + link a tank (if the db fixture happens to have one)
    from fmp.core.database import async_session_factory
    from fmp.models import Tank
    from sqlalchemy import select

    async with async_session_factory() as session:
        tank = (await session.execute(select(Tank))).scalars().first()
        tank_id = str(tank.id) if tank else None

    r = await api.patch(f"/api/v1/iot-gateways/{gw_id}", json={
        "name": "East Gate II", "is_active": True,
    })
    assert r.status_code == 200
    assert r.json()["name"] == "East Gate II" and r.json()["is_active"] is True

    if tank_id:
        r = await api.patch(f"/api/v1/iot-gateways/{gw_id}", json={"tank_ids": [tank_id]})
        assert r.status_code == 200
        assert r.json()["tank_ids"] == [tank_id]
        async with async_session_factory() as session:
            t = await session.get(Tank, tank_id)
            assert str(t.gateway_id) == gw_id

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
