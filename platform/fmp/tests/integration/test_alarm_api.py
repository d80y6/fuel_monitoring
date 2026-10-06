from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from fmp.api.main import app
from fmp.core.database import async_session_factory
from fmp.core.security import hash_password
from fmp.models import Alarm, AuditEvent, Company, Site, Tank, User


@pytest.mark.asyncio
async def test_authenticated_alarm_acknowledgement_persists_actor_and_tenant(db):
    async with async_session_factory() as session:
        company = Company(name="Alarm Operations")
        session.add(company)
        await session.flush()
        site = Site(name="Depot", company_id=company.id)
        session.add(site)
        await session.flush()
        tank = Tank(
            name="Diesel",
            site_id=site.id,
            sensor_serial_number="ALARM-TEST-001",
            tank_diameter=2.0,
            tank_height=3.0,
            tank_volume=9000.0,
        )
        operator = User(
            username="alarm_admin",
            email="alarm-admin@example.test",
            password_hash=hash_password("AlarmPass123!"),
            role="admin",
        )
        session.add_all([tank, operator])
        await session.flush()
        alarm = Alarm(
            tank_id=tank.id,
            timestamp=datetime.now(timezone.utc),
            type="low_level",
            level="WARNING",
            message="Low fuel level",
            value=0.4,
        )
        session.add(alarm)
        await session.commit()
        alarm_id, actor_id, company_id = alarm.id, operator.id, company.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        login = await client.post(
            "/api/v1/auth/login",
            json={"username": "alarm_admin", "password": "AlarmPass123!"},
        )
        assert login.status_code == 200, login.text
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        alarms = await client.get("/api/v1/alarms", headers=headers)
        assert alarms.status_code == 200, alarms.text
        assert [row["id"] for row in alarms.json()] == [str(alarm_id)]
        assert alarms.json()[0]["company_id"] == str(company_id)
        acknowledged = await client.post(f"/api/v1/alarms/{alarm_id}/ack", headers=headers)
        assert acknowledged.status_code == 200, acknowledged.text

    async with async_session_factory() as session:
        persisted = await session.get(Alarm, alarm_id)
        assert persisted.state == "acknowledged"
        assert persisted.acknowledged_by == actor_id
        assert persisted.acknowledged_at.tzinfo is not None
        event = (
            await session.execute(select(AuditEvent).where(AuditEvent.action == "alarm.ack"))
        ).scalar_one()
        assert event.actor_id == actor_id
        assert event.company_id == company_id
        assert event.entity_id == str(alarm_id)
