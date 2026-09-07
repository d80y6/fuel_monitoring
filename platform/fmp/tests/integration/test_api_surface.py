"""Integration test: full API surface against live DB + Redis (via httpx ASGI).

Covers login -> org CRUD -> tank CRUD -> telemetry -> totalizer/authz guards.
Requires Postgres + TimescaleDB; skipped when unreachable.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio


async def test_end_to_end_org_authz(db):
    from fmp.api.main import app

    # --- unauthenticated request is rejected (real dependency, no override) ----
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/v1/companies")
        assert r.status_code == 401 or r.status_code == 403

    # seed an admin and override auth for the authenticated portion
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

    async def _override():
        return admin

    app.dependency_overrides[get_current_user] = _override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = {"Authorization": f"Bearer {token}"}

            # create company -> site -> station -> dispenser -> tank
            r = await client.post("/api/v1/companies", json={"name": f"Acme {uuid.uuid4().hex[:6]}"}, headers=headers)
            assert r.status_code == 201, r.text
            company_id = r.json()["id"]

            r = await client.get("/api/v1/companies", headers=headers)
            assert r.status_code == 200 and len(r.json()) >= 1

            r = await client.post("/api/v1/sites", json={"name": "HQ", "company_id": company_id}, headers=headers)
            assert r.status_code == 201, r.text
            site_id = r.json()["id"]

            r = await client.post("/api/v1/stations", json={
                "name": "Main", "site_id": site_id, "serial_number": f"ST-{uuid.uuid4().hex[:8]}",
            }, headers=headers)
            assert r.status_code == 201, r.text
            station_id = r.json()["id"]

            r = await client.post(f"/api/v1/stations/{station_id}/dispensers", json={
                "name": "P1", "serial_number": f"DN-{uuid.uuid4().hex[:8]}",
            }, headers=headers)
            assert r.status_code == 201, r.text
            dispenser_id = r.json()["id"]

            r = await client.post("/api/v1/tanks", json={
                "name": "Tank1", "site_id": site_id,
                "sensor_serial_number": (tank_serial := f"SN-{uuid.uuid4().hex[:10]}"),
                "tank_orientation": "vertical", "tank_diameter": 2.0, "tank_height": 3.0,
                "tank_volume": 9200.0, "fluid_density": 850.0, "calibration_factor": 1.0,
                "critical_level_threshold": 0.5, "low_level_threshold": 1.0,
                "high_level_threshold": 2.8, "low_volume_threshold": 2000.0,
            }, headers=headers)
            assert r.status_code == 201, r.text
            tank_id = r.json()["id"]

            # duplicate tank serial is rejected with 409
            r = await client.post("/api/v1/tanks", json={
                "name": "TankDup", "site_id": site_id,
                "sensor_serial_number": tank_serial,  # reuse the first tank's serial
                "tank_orientation": "vertical", "tank_diameter": 2.0, "tank_height": 3.0,
                "tank_volume": 9200.0, "fluid_density": 850.0, "calibration_factor": 1.0,
            }, headers=headers)
            assert r.status_code == 409

            # telemetry endpoints + totalizer series
            assert (await client.get(f"/api/v1/tanks/{tank_id}/recent", headers=headers)).status_code == 200
            assert (await client.get(f"/api/v1/tanks/{tank_id}/alarms", headers=headers)).status_code == 200
            r = await client.get(f"/api/v1/totalizers?dispenser_id={dispenser_id}", headers=headers)
            assert r.status_code == 200
    finally:
        app.dependency_overrides.clear()


async def test_login_and_me(db):
    """Real credential path: login issues a token that /me accepts."""
    from fmp.api.main import app
    from fmp.core.database import async_session_factory
    from fmp.core.security import hash_password
    from fmp.models import User

    async with async_session_factory() as session:
        session.add(User(
            username="operator", email="op@t.io",
            password_hash=hash_password("OpPass123"), role="user", is_active=True,
        ))
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/api/v1/auth/login", json={
            "username": "operator", "password": "OpPass123",
        })
        assert r.status_code == 200, r.text
        token = r.json()["access_token"]
        assert r.json()["user"]["username"] == "operator"

        me = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me.status_code == 200
        assert me.json()["id"] == r.json()["user"]["id"]

        # wrong password rejected
        bad = await client.post("/api/v1/auth/login", json={
            "username": "operator", "password": "WrongPass",
        })
        assert bad.status_code == 401