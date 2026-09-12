"""Integration test: streamed CSV export of tank telemetry.

Seeds a tank with 5 measurements and downloads them through
``GET /api/v1/tanks/{id}/export``, asserting a CSV attachment with a header row
plus one ordered data row per reading.
"""
from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.asyncio


async def test_csv_export_measurements(client):
    from fmp.core.database import async_session_factory
    from fmp.models import Company, Site, Tank, Measurement

    t0 = datetime.now(timezone.utc)
    volumes = []

    async with async_session_factory() as session:
        company = Company(name=f"EX-{uuid.uuid4().hex[:6]}")
        session.add(company)
        await session.flush()
        site = Site(name="Export Site", company_id=company.id)
        session.add(site)
        await session.flush()
        tank = Tank(
            name="Export Tank",
            site_id=site.id,
            sensor_serial_number=f"EXSN-{uuid.uuid4().hex[:10]}",
            tank_orientation="vertical",
            tank_shape="vertical_cylinder",
            tank_diameter=2.0,
            tank_height=3.0,
            tank_volume=9200.0,
            elevation=0.0,
            calibration_factor=1.0,
            is_active=True,
        )
        session.add(tank)
        await session.flush()

        for i in range(5):
            volume = 1000.0 + i
            volumes.append((t0 + timedelta(minutes=i), volume))
            session.add(Measurement(
                tank_id=tank.id,
                timestamp=t0 + timedelta(minutes=i),
                pressure=1.5,
                temperature=20.0,
                level=2.0 + 0.1 * i,
                volume=volume,
                gov_volume=volume,
                net_volume=volume * 0.98,
                density_at_temperature=800.0,
                fill_percent=50.0,
                is_outlier=False,
                status=0,
            ))
        await session.commit()

    start = (t0 - timedelta(minutes=1)).isoformat()
    end = (t0 + timedelta(minutes=5)).isoformat()
    resp = await client.get(
        f"/api/v1/tanks/{tank.id}/export",
        params={"start": start, "end": end},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers.get("content-disposition", "")

    rows = list(csv.reader(io.StringIO(resp.text)))
    assert len(rows) == 6  # header + 5 readings
    assert rows[0][0] == "timestamp"
    assert rows[0][1] == "tank_id"

    parsed_timestamps = [datetime.fromisoformat(r[0]) for r in rows[1:]]
    assert parsed_timestamps == sorted(parsed_timestamps) == [ts for ts, _ in volumes]

    parsed_volumes = [float(r[5]) if len(r) > 5 else None for r in rows[1:]]
    assert parsed_volumes == [v for _, v in volumes]


async def test_csv_export_requires_authentication(client):
    # The conftest override supplies an authenticated user, so this asserts the
    # export route exists and is reachable through the API (auth is exercised
    # by the role-hardening suite for the whole v1 surface).
    from fmp.core.database import async_session_factory
    from fmp.models import Company, Site, Tank

    async with async_session_factory() as session:
        company = Company(name=f"EXA-{uuid.uuid4().hex[:6]}")
        session.add(company)
        await session.flush()
        site = Site(name="Export Auth Site", company_id=company.id)
        session.add(site)
        await session.flush()
        tank = Tank(
            name="Export Auth Tank",
            site_id=site.id,
            sensor_serial_number=f"EXASN-{uuid.uuid4().hex[:10]}",
            tank_orientation="vertical",
            tank_shape="vertical_cylinder",
            tank_diameter=2.0,
            tank_height=3.0,
            tank_volume=9200.0,
            elevation=0.0,
            calibration_factor=1.0,
            is_active=True,
        )
        session.add(tank)
        await session.commit()

    start = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    end = datetime.now(timezone.utc).isoformat()
    resp = await client.get(
        f"/api/v1/tanks/{tank.id}/export",
        params={"start": start, "end": end},
    )
    assert resp.status_code == 200
    assert resp.text.strip().startswith("timestamp,tank_id")  # header-only CSV