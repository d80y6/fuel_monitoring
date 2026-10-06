"""Tenant-isolation regression suite (audit G-003, workflow 10).

Two organizations with structurally identical assets are created, then every
tenant-scoped endpoint is exercised as **both** tenants. The suite asserts three
things for each endpoint:

1. each tenant sees only its own rows,
2. a tenant cannot reach the other tenant's row by substituting an id in the
   path, query string or request body,
3. the platform administrator still sees everything.

This is the test that would have caught the original cross-tenant exposure, where
``list_tanks`` / ``list_sites`` / alarms / dispensing / telemetry all returned
every organization's data to any authenticated caller.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from redis import Redis as SyncRedis
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from fmp.api.main import app
from fmp.core.database import async_session_factory
from fmp.core.security import hash_password
from fmp.core.config import get_settings
from fmp.ingestion.pipeline import LIVE_CHANNEL
from fmp.models import (
    Alarm,
    Allocation,
    Company,
    Dispenser,
    Employee,
    Site,
    Station,
    Tank,
    UploadBatch,
    User,
)


@pytest_asyncio.fixture
async def two_tenants(db):
    """Two organizations, each with a site, station, dispenser, tank and user.

    Mirrors the real graph so the scoping rules are exercised end to end:
    Tank -> Site -> Company, Station -> Site -> Company, Allocation -> Company.
    """
    created: dict = {}
    async with async_session_factory() as session:
        for label in ("alpha", "beta"):
            company = Company(name=f"{label}-corp")
            session.add(company)
            await session.flush()

            admin = User(
                username=f"{label}_admin",
                email=f"{label}-admin@example.test",
                password_hash=hash_password(f"{label.capitalize()}Pass123!"),
                role="company_admin",
                company_id=company.id,
            )
            operator = User(
                username=f"{label}_user",
                email=f"{label}-user@example.test",
                password_hash=hash_password(f"{label.capitalize()}User123!"),
                role="user",
                company_id=company.id,
            )
            session.add_all([admin, operator])
            await session.flush()

            site = Site(name=f"{label}-site", company_id=company.id)
            session.add(site)
            await session.flush()

            station = Station(
                name=f"{label}-station",
                site_id=site.id,
                serial_number=f"ST-{label.upper()}-1",
            )
            session.add(station)
            await session.flush()

            dispenser = Dispenser(
                name=f"{label}-pump",
                station_id=station.id,
                serial_number=f"DN-{label.upper()}-1",
            )
            session.add(dispenser)
            await session.flush()

            tank = Tank(
                name=f"{label}-tank",
                site_id=site.id,
                sensor_serial_number=f"SN-{label.upper()}-1",
                tank_diameter=2.0,
                tank_height=4.0,
                tank_volume=12000.0,
                low_level_threshold=0.5,
            )
            session.add(tank)
            await session.flush()

            employee = Employee(
                employee_id=f"EMP-{label.upper()}",
                name=f"{label} employee",
                phone="+1000000000",
                company_id=company.id,
            )
            session.add(employee)
            await session.flush()

            batch = UploadBatch(
                filename=f"{label}.csv",
                original_filename=f"{label}.csv",
                uploaded_by_id=admin.id,
                total_rows=1,
                successful_rows=1,
                failed_rows=0,
                status="COMPLETED",
            )
            session.add(batch)
            await session.flush()

            allocation = Allocation(
                employee_id=employee.id,
                upload_batch_id=batch.id,
                company_id=company.id,
                invoice_number=f"INV-{label.upper()}",
                allocated_liters=100.0,
                remaining_liters=100.0,
            )
            session.add(allocation)
            await session.flush()

            alarm = Alarm(
                tank_id=tank.id,
                timestamp=datetime.now(UTC),
                type="low_level",
                level="WARNING",
                message=f"{label} low level",
                value=0.3,
            )
            session.add(alarm)
            await session.flush()

            created[label] = {
                "company_id": company.id,
                "site_id": site.id,
                "station_id": station.id,
                "dispenser_id": dispenser.id,
                "tank_id": tank.id,
                "allocation_id": allocation.id,
                "alarm_id": alarm.id,
                "admin_id": admin.id,
                "operator_id": operator.id,
                "admin_username": admin.username,
                "admin_password": f"{label.capitalize()}Pass123!",
                "user_username": operator.username,
                "user_password": f"{label.capitalize()}User123!",
            }

        platform_admin = User(
            username="platform_root",
            email="root@example.test",
            password_hash=hash_password("RootPass123!"),
            role="admin",
            company_id=None,
        )
        session.add(platform_admin)
        await session.commit()
        created["platform"] = {"username": "platform_root", "password": "RootPass123!"}
    return created


def publish(channel: str, payload: str) -> None:
    """Publish straight to Redis so the socket's own subscription path is tested."""
    settings = get_settings()
    client = SyncRedis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD,
        socket_timeout=5,
    )
    try:
        client.publish(channel, payload)
    finally:
        client.close()


@pytest_asyncio.fixture
async def anon_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _login(client: AsyncClient, username: str, password: str) -> dict:
    resp = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest_asyncio.fixture
async def alpha_admin(anon_client, two_tenants):
    return await _login(
        anon_client,
        two_tenants["alpha"]["admin_username"],
        two_tenants["alpha"]["admin_password"],
    )


# ---------------------------------------------------------------------------
# List endpoints: a tenant sees exactly its own rows
# ---------------------------------------------------------------------------
LIST_CASES = [
    ("/api/v1/tanks", "tank_id"),
    ("/api/v1/sites", "site_id"),
    ("/api/v1/stations", "station_id"),
    ("/api/v1/companies", "company_id"),
    ("/api/v1/alarms", "alarm_id"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("path,key", LIST_CASES)
async def test_tenant_sees_only_own_rows(two_tenants, anon_client, path, key):
    """Each tenant's list response contains its own ids and never the other's."""
    for tenant, other in (("alpha", "beta"), ("beta", "alpha")):
        headers = await _login(
            anon_client,
            two_tenants[tenant]["admin_username"],
            two_tenants[tenant]["admin_password"],
        )
        resp = await anon_client.get(path, headers=headers)
        assert resp.status_code == 200, resp.text
        returned = {row["id"] for row in resp.json()}
        foreign = str(two_tenants[other][key])
        assert foreign not in returned, f"{path}: {tenant} saw {other}'s {key}"
        own = str(two_tenants[tenant][key])
        assert own in returned, f"{path}: {tenant} cannot see its own {key}"


@pytest.mark.asyncio
async def test_platform_admin_sees_all_tenants(two_tenants, anon_client):
    headers = await _login(
        anon_client, two_tenants["platform"]["username"], two_tenants["platform"]["password"]
    )
    tanks = (await anon_client.get("/api/v1/tanks", headers=headers)).json()
    ids = {row["id"] for row in tanks}
    assert {str(two_tenants["alpha"]["tank_id"]), str(two_tenants["beta"]["tank_id"])} <= ids

    companies = (await anon_client.get("/api/v1/companies", headers=headers)).json()
    assert {"alpha-corp", "beta-corp"} <= {row["name"] for row in companies}


# ---------------------------------------------------------------------------
# Single-resource endpoints: id substitution must not cross the boundary
# ---------------------------------------------------------------------------
GET_BY_ID_CASES = [
    ("/api/v1/tanks/{tank_id}", "tank_id"),
    ("/api/v1/sites/{site_id}", "site_id"),
    ("/api/v1/stations/{station_id}", "station_id"),
    ("/api/v1/companies/{company_id}", "company_id"),
    ("/api/v1/analytics/consumption/{tank_id}", "tank_id"),
    ("/api/v1/tanks/{tank_id}/recent", "tank_id"),
    ("/api/v1/tanks/{tank_id}/alarms", "tank_id"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("template,key", GET_BY_ID_CASES)
async def test_tenant_cannot_read_foreign_resource_by_id(
    two_tenants, anon_client, alpha_admin, template, key
):
    """alpha's admin requesting beta's resource must get 404, and its own must work."""
    foreign = await anon_client.get(
        template.format(**{key: two_tenants["beta"][key]}), headers=alpha_admin
    )
    assert foreign.status_code == 404, f"{template} leaked: {foreign.status_code} {foreign.text}"

    own = await anon_client.get(
        template.format(**{key: two_tenants["alpha"][key]}), headers=alpha_admin
    )
    assert own.status_code == 200, own.text


@pytest.mark.asyncio
async def test_tenant_cannot_ack_or_resolve_foreign_alarm(two_tenants, anon_client, alpha_admin):
    foreign_alarm = two_tenants["beta"]["alarm_id"]
    ack = await anon_client.post(f"/api/v1/alarms/{foreign_alarm}/ack", headers=alpha_admin)
    assert ack.status_code == 404, ack.text
    resolve = await anon_client.post(f"/api/v1/alarms/{foreign_alarm}/resolve", headers=alpha_admin)
    assert resolve.status_code == 404, resolve.text


@pytest.mark.asyncio
async def test_tenant_cannot_mutate_foreign_resources(two_tenants, anon_client, alpha_admin):
    beta = two_tenants["beta"]
    cases = [
        ("patch", f"/api/v1/tanks/{beta['tank_id']}", {"name": "hijacked"}),
        ("delete", f"/api/v1/sites/{beta['site_id']}", None),
        ("delete", f"/api/v1/stations/{beta['station_id']}", None),
        (
            "delete",
            f"/api/v1/stations/{beta['station_id']}/dispensers/{beta['dispenser_id']}",
            None,
        ),
        ("patch", f"/api/v1/sites/{beta['site_id']}", {"name": "hijacked"}),
        ("patch", f"/api/v1/stations/{beta['station_id']}", {"name": "hijacked"}),
    ]
    for method, path, payload in cases:
        resp = await anon_client.request(method, path, headers=alpha_admin, json=payload)
        assert resp.status_code == 404, f"{method.upper()} {path} leaked: {resp.status_code}"


@pytest.mark.asyncio
async def test_tenant_cannot_read_or_write_foreign_strapping(
    two_tenants, anon_client, alpha_admin
):
    """Calibration data is tenant-bound; the original code let anyone overwrite it."""
    foreign_tank = two_tenants["beta"]["tank_id"]
    read = await anon_client.get(f"/api/v1/tanks/{foreign_tank}/strapping", headers=alpha_admin)
    assert read.status_code == 404, read.text
    write = await anon_client.put(
        f"/api/v1/tanks/{foreign_tank}/strapping",
        headers=alpha_admin,
        json={
            "calibration_data": [
                {"height": 0.0, "volume": 0.0},
                {"height": 4.0, "volume": 12000.0},
            ]
        },
    )
    assert write.status_code == 404, write.text


@pytest.mark.asyncio
async def test_tenant_cannot_export_foreign_telemetry(two_tenants, anon_client, alpha_admin):
    resp = await anon_client.get(
        f"/api/v1/tanks/{two_tenants['beta']['tank_id']}/export",
        headers=alpha_admin,
        params={"start": "2020-01-01T00:00:00Z", "end": "2030-01-01T00:00:00Z"},
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_tenant_cannot_read_foreign_totalizers(two_tenants, anon_client, alpha_admin):
    resp = await anon_client.get(
        f"/api/v1/totalizers?dispenser_id={two_tenants['beta']['dispenser_id']}",
        headers=alpha_admin,
    )
    assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# Dispensing
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_dispensing_lists_are_tenant_scoped(two_tenants, anon_client, alpha_admin):
    allocations = await anon_client.get("/api/v1/dispensing/allocations", headers=alpha_admin)
    assert allocations.status_code == 200, allocations.text
    ids = {row["id"] for row in allocations.json()}
    assert str(two_tenants["beta"]["allocation_id"]) not in ids
    assert str(two_tenants["alpha"]["allocation_id"]) in ids

    transactions = await anon_client.get("/api/v1/dispensing/transactions", headers=alpha_admin)
    assert transactions.status_code == 200, transactions.text


@pytest.mark.asyncio
async def test_upload_rejects_cross_tenant_company(two_tenants, anon_client, alpha_admin):
    """A tenant admin cannot mint authorization codes for another organization."""
    resp = await anon_client.post(
        "/api/v1/dispensing/upload",
        headers=alpha_admin,
        files={"file": ("quota.csv", b"Employee ID,Name,Phone,Liters\n", "text/csv")},
        data={"company_id": str(two_tenants["beta"]["company_id"])},
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_dispensing_device_endpoints_require_a_station_key(
    two_tenants, anon_client, alpha_admin
):
    """validate/complete are device endpoints, not operator endpoints."""
    beta_station = two_tenants["beta"]["station_id"]
    body = {
        "code": "123456",
        "station_id": str(beta_station),
        "requested_liters": 10.0,
    }
    anonymous = await anon_client.post("/api/v1/dispensing/validate", json=body)
    assert anonymous.status_code == 401, anonymous.text

    operator_token = await anon_client.post(
        "/api/v1/dispensing/validate", headers=alpha_admin, json=body
    )
    assert operator_token.status_code == 401, (
        f"an operator JWT must not authenticate as a device: {operator_token.status_code}"
    )

    wrong_key = await anon_client.post(
        "/api/v1/dispensing/validate",
        headers={"X-Station-Id": str(beta_station), "X-Station-Key": "fmk_wrong"},
        json=body,
    )
    assert wrong_key.status_code == 401, wrong_key.text


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_users_are_tenant_scoped(two_tenants, anon_client, alpha_admin):
    listing = await anon_client.get("/api/v1/users", headers=alpha_admin)
    assert listing.status_code == 200, listing.text
    usernames = {row["username"] for row in listing.json()}
    assert two_tenants["alpha"]["user_username"] in usernames
    assert two_tenants["beta"]["admin_username"] not in usernames
    # Platform admins must not leak into a tenant's directory.
    assert two_tenants["platform"]["username"] not in usernames

    foreign = await anon_client.get(
        f"/api/v1/users/{two_tenants['beta']['admin_id']}", headers=alpha_admin
    )
    assert foreign.status_code in (403, 404), foreign.text


# ---------------------------------------------------------------------------
# Anonymous access is rejected everywhere
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/v1/tanks"),
        ("get", "/api/v1/sites"),
        ("get", "/api/v1/alarms"),
        ("get", "/api/v1/users"),
        ("get", "/api/v1/companies"),
        ("get", "/api/v1/notification-gateways"),
        ("get", "/api/v1/notification-rules"),
        ("get", "/api/v1/notifications/logs"),
        ("get", "/api/v1/realtime/metrics"),
        ("get", "/api/v1/dispensing/allocations"),
        ("get", "/api/v1/dispensing/transactions"),
        ("get", "/api/v1/iot-gateways"),
    ],
)
async def test_anonymous_is_rejected(anon_client, method, path):
    resp = await anon_client.request(method, path)
    assert resp.status_code in (401, 403), f"{path} allowed anonymous: {resp.status_code}"


# ---------------------------------------------------------------------------
# WebSocket streaming must not cross the tenant boundary
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ws_event_filtering_is_tenant_scoped():
    from fmp.api.v1.realtime import _event_visible
    from fmp.models import User

    import uuid

    alpha_company = uuid.uuid4()
    beta_company = uuid.uuid4()
    alpha_user = User(username="a", role="user", company_id=alpha_company)
    beta_user = User(username="b", role="user", company_id=beta_company)
    platform_user = User(username="p", role="admin", company_id=None)

    own = {"company_id": str(alpha_company)}
    foreign = {"company_id": str(beta_company)}
    untagged = {"company_id": None}

    assert _event_visible(own, alpha_user) is True
    assert _event_visible(foreign, alpha_user) is False
    assert _event_visible(own, beta_user) is False
    # Untagged events are refused rather than leaked.
    assert _event_visible(untagged, alpha_user) is False
    # Platform operator sees everything.
    assert _event_visible(foreign, platform_user) is True
    assert _event_visible(own, platform_user) is True
    assert _event_visible(untagged, platform_user) is True


def test_real_websocket_only_receives_own_tenant_events(two_tenants):
    """End-to-end: alpha's socket must not observe beta's published telemetry.

    Synchronous on purpose. The WebSocket handler opens its own connections on
    the loop Starlette's TestClient portal provides, so driving it from the
    pytest-asyncio loop would reuse pooled asyncpg connections across loops.
    """
    import asyncio
    import json

    async def _dispose():
        from fmp.core.database import engine

        await engine.dispose()

    # The async fixtures above opened pooled connections on the pytest-asyncio
    # loop; Starlette's TestClient serves on its own loop, so drop the pool first
    # rather than handing it a connection bound to a closed loop.
    asyncio.run(_dispose())

    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={
                "username": two_tenants["alpha"]["admin_username"],
                "password": two_tenants["alpha"]["admin_password"],
            },
        )
        assert login.status_code == 200, login.text
        token = login.json()["access_token"]

        with client.websocket_connect(
            f"/ws/telemetry?token={token}&channels=telemetry"
        ) as ws:
            publish(
                LIVE_CHANNEL,
                json.dumps(
                    {
                        "tank_id": str(two_tenants["beta"]["tank_id"]),
                        "company_id": str(two_tenants["beta"]["company_id"]),
                        "level": 1.0,
                    }
                ),
            )
            publish(
                LIVE_CHANNEL,
                json.dumps(
                    {
                        "tank_id": str(two_tenants["alpha"]["tank_id"]),
                        "company_id": str(two_tenants["alpha"]["company_id"]),
                        "level": 2.0,
                    }
                ),
            )
            received = []
            for _ in range(40):
                try:
                    received.append(ws.receive_json())
                except (WebSocketDisconnect, TimeoutError):
                    break
                if received[-1].get("level") == 2.0:
                    break

    beta_company = str(two_tenants["beta"]["company_id"])
    assert received, "no telemetry reached the socket at all"
    assert all(msg.get("company_id") != beta_company for msg in received), (
        f"alpha's socket received beta's telemetry: {received}"
    )


