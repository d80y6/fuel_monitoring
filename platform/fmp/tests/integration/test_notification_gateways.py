"""Integration test: notification-gateway CRUD API against live DB."""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def token_override(db):
    from fmp.core.database import async_session_factory
    from fmp.core.security import hash_password
    from fmp.models import User
    from fmp.api.deps import get_current_user
    from fmp.core.security import create_access_token

    pw = hash_password("AdminPass123")
    async with async_session_factory() as session:
        admin = User(
            username="root", email="root@t.io", password_hash=pw,
            role="admin", is_active=True,
        )
        session.add(admin)
        await session.commit()
    token = create_access_token(admin.id, extra={"role": "admin"})

    from fmp.api.main import app

    async def _override():
        return admin

    app.dependency_overrides[get_current_user] = _override
    try:
        yield token
    finally:
        app.dependency_overrides.clear()


async def test_gateway_crud(token_override):
    from fmp.api.main import app

    headers = {"Authorization": f"Bearer {token_override}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # create
        r = await client.post("/api/v1/notification-gateways", headers=headers, json={
            "name": "SMPP-1", "type": "smpp", "config_json": {"host": "sms.gw"},
        })
        assert r.status_code == 201, r.text
        body = r.json()
        gw_id = body["id"]
        assert body["is_active"] is True and body["priority"] == 10
        assert body["config_json"] == {"host": "sms.gw"}

        # duplicate name → 409
        r = await client.post("/api/v1/notification-gateways", headers=headers, json={
            "name": "SMPP-1", "type": "whatsapp",
        })
        assert r.status_code == 409

        # create second gateway for list filter checks
        r = await client.post("/api/v1/notification-gateways", headers=headers, json={
            "name": "WA-1", "type": "whatsapp", "config_json": {"token": "abc"},
        })
        assert r.status_code == 201
        wa_id = r.json()["id"]

        # list + type filter
        r = await client.get("/api/v1/notification-gateways", headers=headers)
        assert r.status_code == 200 and len(r.json()) == 2
        r = await client.get("/api/v1/notification-gateways?type=smpp", headers=headers)
        assert r.status_code == 200 and [g["id"] for g in r.json()] == [gw_id]

        # patch priority + inactive
        r = await client.patch(f"/api/v1/notification-gateways/{gw_id}", headers=headers, json={
            "priority": 5, "is_active": False,
        })
        assert r.status_code == 200
        assert r.json()["priority"] == 5 and r.json()["is_active"] is False

        # delete → gone from list
        r = await client.delete(f"/api/v1/notification-gateways/{wa_id}", headers=headers)
        assert r.status_code == 204
        r = await client.get("/api/v1/notification-gateways", headers=headers)
        assert r.status_code == 200 and len(r.json()) == 1

        # delete missing → 404
        import uuid
        r = await client.delete(f"/api/v1/notification-gateways/{uuid.uuid4()}", headers=headers)
        assert r.status_code == 404

        # get single
        r = await client.get(f"/api/v1/notification-gateways/{gw_id}", headers=headers)
        assert r.status_code == 200 and r.json()["is_active"] is False