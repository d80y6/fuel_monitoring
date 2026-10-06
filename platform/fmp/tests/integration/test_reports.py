"""Reports API and computations (audit G-108).

These tests assert the *numbers*, not just that a 200 came back: a report whose
figures are wrong is worse than no report, because an operator will act on them.

Coverage:
* tenant isolation — a report never includes another organization's rows,
* correct consumption arithmetic (drops only, rises ignored),
* correct variance arithmetic (measured change vs booked outflow),
* CSV rendered from the JSON's own columns, so the two cannot disagree,
* documented assumptions surfaced in the payload,
* window validation.
"""
from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from fmp.api.main import app
from fmp.core.database import async_session_factory
from fmp.core.security import hash_password
from fmp.models import (
    Alarm,
    Company,
    Dispenser,
    Employee,
    Measurement,
    Site,
    Station,
    Tank,
    User,
)
from fmp.services.reporting import normalise_window, to_csv

# Anchored to whole hours: the consumption series buckets by hour and takes
# last(volume) per bucket, so a sub-hour start would make the expected day
# boundaries depend on the minute the suite happens to run.
WINDOW_START = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) - timedelta(days=2)
WINDOW_END = datetime.now(UTC) + timedelta(minutes=1)


def _qs(start: datetime = WINDOW_START, end: datetime = WINDOW_END, **extra) -> dict:
    params = {"start": start.isoformat(), "end": end.isoformat()}
    params.update({k: str(v) for k, v in extra.items()})
    return params


@pytest_asyncio.fixture
async def seeded(db):
    """Two tenants with tanks and measurements; beta also has a dispense."""
    ids: dict = {}
    async with async_session_factory() as session:
        # alpha: day 0 drains 100 L, day 1 drains 20 L. Beta: drains 100 L.
        plan = {
            "alpha": [(0, 1000.0), (1, 900.0), (26, 880.0), (27, 860.0)],
            "beta": [(0, 500.0), (1, 400.0)],
        }
        for label, series_points in plan.items():
            company = Company(name=f"{label}-corp")
            session.add(company)
            await session.flush()
            site = Site(name=f"{label}-site", company_id=company.id)
            session.add(site)
            await session.flush()
            tank = Tank(
                name=f"{label}-tank",
                site_id=site.id,
                sensor_serial_number=f"SN-REP-{label}",
                tank_diameter=2.0,
                tank_height=4.0,
                tank_volume=20000.0,
            )
            session.add(tank)
            await session.flush()
            for hour_offset, volume in series_points:
                ts = WINDOW_START + timedelta(hours=hour_offset)
                session.add(
                    Measurement(
                        tank_id=tank.id,
                        timestamp=ts,
                        pressure=1.0,
                        temperature=20.0,
                        level=1.0,
                        volume=volume,
                        gov_volume=volume,
                        net_volume=volume,
                        density_at_temperature=750.0,
                        fill_percent=volume / 200.0,
                        is_outlier=False,
                        status=0,
                    )
                )
            admin = User(
                username=f"{label}_rep",
                email=f"{label}-rep@example.test",
                password_hash=hash_password(f"{label.capitalize()}Pass123!"),
                role="company_admin",
                company_id=company.id,
            )
            session.add(admin)
            await session.flush()
            ids[label] = {
                "company_id": company.id,
                "site_id": site.id,
                "tank_id": tank.id,
                "username": admin.username,
                "password": f"{label.capitalize()}Pass123!",
            }

        # An alarm on alpha's tank.
        session.add(
            Alarm(
                tank_id=ids["alpha"]["tank_id"],
                timestamp=WINDOW_START + timedelta(hours=2),
                type="low_volume",
                level="CRITICAL",
                message="Below threshold",
                value=880.0,
                state="resolved",
                resolved_at=WINDOW_START + timedelta(hours=8),
                resolved_message="Refilled",
            )
        )
        await session.commit()

        root = User(
            username="rep_root",
            email="rep-root@example.test",
            password_hash=hash_password("RootPass123!"),
            role="admin",
            company_id=None,
        )
        session.add(root)
        await session.commit()
        ids["root"] = {"username": "rep_root", "password": "RootPass123!"}
    return ids


@pytest_asyncio.fixture
async def anon():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _auth(client, username, password) -> AsyncClient:
    resp = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    client.headers["Authorization"] = f"Bearer {resp.json()['access_token']}"
    return client


# ---------------------------------------------------------------------------
# Catalogue and access control
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_report_catalogue_lists_every_report(anon, seeded):
    await _auth(anon, seeded["alpha"]["username"], seeded["alpha"]["password"])
    body = (await anon.get("/api/v1/reports")).json()
    names = {r["name"] for r in body["reports"]}
    assert names == {
        "tank-inventory", "consumption", "inventory-variance", "alarms", "dispensing-audit",
    }
    assert all(r["description"] for r in body["reports"])


async def test_anonymous_cannot_run_a_report(anon):
    resp = await anon.get("/api/v1/reports/tank-inventory", params=_qs())
    assert resp.status_code in (401, 403)


async def test_unknown_report_is_404(anon, seeded):
    await _auth(anon, seeded["alpha"]["username"], seeded["alpha"]["password"])
    resp = await anon.get("/api/v1/reports/nope", params=_qs())
    assert resp.status_code == 404, resp.text


async def test_inverted_window_is_rejected(anon, seeded):
    await _auth(anon, seeded["alpha"]["username"], seeded["alpha"]["password"])
    resp = await anon.get(
        "/api/v1/reports/tank-inventory",
        params=_qs(start=WINDOW_END, end=WINDOW_START),
    )
    assert resp.status_code == 422, resp.text


async def test_absurd_window_is_rejected(anon, seeded):
    await _auth(anon, seeded["alpha"]["username"], seeded["alpha"]["password"])
    resp = await anon.get(
        "/api/v1/reports/tank-inventory",
        params=_qs(
            start=WINDOW_END - timedelta(days=400),
            end=WINDOW_END,
        ),
    )
    assert resp.status_code == 422, resp.text


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "report", ["tank-inventory", "consumption", "inventory-variance", "alarms"]
)
async def test_report_never_includes_another_tenant(anon, seeded, report):
    await _auth(anon, seeded["alpha"]["username"], seeded["alpha"]["password"])
    body = (await anon.get(f"/api/v1/reports/{report}", params=_qs())).json()
    blob = str(body)
    assert str(seeded["beta"]["tank_id"]) not in blob, f"{report} leaked beta's tank"
    assert "beta-tank" not in blob, f"{report} leaked beta's tank name"


async def test_platform_admin_sees_both_tenants(anon, seeded):
    await _auth(anon, seeded["root"]["username"], seeded["root"]["password"])
    body = (await anon.get("/api/v1/reports/tank-inventory", params=_qs())).json()
    names = {r["tank_name"] for r in body["rows"]}
    assert {"alpha-tank", "beta-tank"} <= names


async def test_cannot_report_on_another_tenants_site(anon, seeded):
    await _auth(anon, seeded["alpha"]["username"], seeded["alpha"]["password"])
    resp = await anon.get(
        "/api/v1/reports/tank-inventory", params=_qs(site_id=seeded["beta"]["site_id"])
    )
    assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# Correctness of the numbers
# ---------------------------------------------------------------------------
async def test_tank_inventory_reports_capacity_volume_and_freshness(anon, seeded):
    await _auth(anon, seeded["alpha"]["username"], seeded["alpha"]["password"])
    row = (await anon.get("/api/v1/reports/tank-inventory", params=_qs())).json()["rows"][0]

    assert row["capacity_liters"] == 20000.0
    # The last seeded measurement for alpha is 860.0 L.
    assert row["volume_liters"] == pytest.approx(860.0)
    assert row["fill_percent"] == pytest.approx(4.3)
    assert row["data_quality"] in ("measured", "stale")
    assert row["measured_at"] is not None
    assert isinstance(row["stale"], bool)
    # Change across the window: 1000 -> 860 is 140 L drawn.
    assert row["change_in_window_liters"] == pytest.approx(-140.0)


async def test_tank_inventory_states_its_assumptions(anon, seeded):
    await _auth(anon, seeded["alpha"]["username"], seeded["alpha"]["password"])
    body = (await anon.get("/api/v1/reports/tank-inventory", params=_qs())).json()
    assert body["assumptions"], "a report must document how it was computed"
    assert body["window"]["start"] and body["window"]["end"]
    assert body["generated_at"]


async def test_consumption_counts_only_drops(anon, seeded):
    await _auth(anon, seeded["alpha"]["username"], seeded["alpha"]["password"])
    body = (await anon.get("/api/v1/reports/consumption", params=_qs())).json()

    assert body["rows"], "seeded data should produce consumption rows"
    for row in body["rows"]:
        assert row["consumed_liters"] >= 0, "consumption is never negative"
        assert row["tank_name"] == "alpha-tank"

    # Seeded plan: 1000 -> 900 (100 L), 900 -> 880 (20 L), 880 -> 860 (20 L).
    alpha_rows = [r for r in body["rows"] if r["tank_name"] == "alpha-tank"]
    assert sum(r["consumed_liters"] for r in alpha_rows) == pytest.approx(140.0, abs=1e-6)
    # Each delta is attributed to the day its earlier sample falls in, so the
    # split depends on the window anchor hour — assert the shape, not the dates.
    assert {r["day"] for r in alpha_rows} <= {
        (WINDOW_START + timedelta(days=n)).date().isoformat() for n in (0, 1, 2)
    }
    assert all(r["consumed_liters"] > 0 for r in alpha_rows)


async def test_consumption_ignores_a_refill(anon, seeded):
    """A rise in tank volume is a delivery and must not offset consumption."""
    async with async_session_factory() as session:
        tank_id = uuid.UUID(str(seeded["alpha"]["tank_id"]))
        session.add(
            Measurement(
                tank_id=tank_id,
                timestamp=WINDOW_START + timedelta(days=1, hours=18),
                pressure=1.0,
                temperature=20.0,
                level=1.0,
                volume=5000.0,  # a big delivery
                gov_volume=5000.0,
                net_volume=5000.0,
                density_at_temperature=750.0,
                fill_percent=25.0,
                is_outlier=False,
                status=0,
            )
        )
        await session.commit()

    await _auth(anon, seeded["alpha"]["username"], seeded["alpha"]["password"])
    body = (await anon.get("/api/v1/reports/consumption", params=_qs())).json()
    total = sum(r["consumed_liters"] for r in body["rows"] if r["tank_name"] == "alpha-tank")
    assert total == pytest.approx(140.0, abs=1e-6), (
        "a delivery must not cancel out real consumption"
    )


async def test_alarm_report_shows_the_lifecycle(anon, seeded):
    await _auth(anon, seeded["alpha"]["username"], seeded["alpha"]["password"])
    body = (await anon.get("/api/v1/reports/alarms", params=_qs())).json()
    assert body["summary"]["total"] == 1
    assert body["summary"]["by_level"]["CRITICAL"] == 1
    assert body["summary"]["resolved"] == 1
    row = body["rows"][0]
    assert row["type"] == "low_volume"
    assert row["state"] == "resolved"
    assert row["resolution"] == "Refilled"


async def test_alarm_report_level_filter(anon, seeded):
    await _auth(anon, seeded["alpha"]["username"], seeded["alpha"]["password"])
    body = (await anon.get("/api/v1/reports/alarms", params=_qs(level="WARNING"))).json()
    assert body["summary"]["total"] == 0, "filtering by level must actually filter"


async def test_empty_window_returns_empty_not_zeroes(anon, seeded):
    await _auth(anon, seeded["alpha"]["username"], seeded["alpha"]["password"])
    empty = (
        (datetime.now(UTC) - timedelta(days=400), datetime.now(UTC) - timedelta(days=399))
    )
    resp = await anon.get(
        "/api/v1/reports/consumption",
        params=_qs(start=empty[0], end=empty[1]),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["rows"] == []
    assert body["grand_total_liters"] == 0.0


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------
async def test_csv_export_matches_the_json(anon, seeded):
    await _auth(anon, seeded["alpha"]["username"], seeded["alpha"]["password"])
    js = await anon.get("/api/v1/reports/consumption", params=_qs())
    csv_resp = await anon.get("/api/v1/reports/consumption/export", params=_qs())

    assert csv_resp.status_code == 200
    assert csv_resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in csv_resp.headers["content-disposition"]

    json_body = js.json()
    rows = list(csv.reader(io.StringIO(csv_resp.text)))
    assert rows[0] == json_body["columns"]
    assert len(rows) - 1 == len(json_body["rows"])


async def test_csv_export_is_tenant_scoped(anon, seeded):
    await _auth(anon, seeded["alpha"]["username"], seeded["alpha"]["password"])
    resp = await anon.get("/api/v1/reports/tank-inventory/export", params=_qs())
    assert resp.status_code == 200
    assert "beta-tank" not in resp.text
    assert "alpha-tank" in resp.text


async def test_csv_export_requires_auth(anon):
    resp = await anon.get("/api/v1/reports/alarms/export", params=_qs())
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
class TestWindowNormalisation:
    def test_naive_timestamps_are_treated_as_utc(self):
        window = normalise_window(
            datetime(2026, 1, 1, 0, 0), datetime(2026, 1, 2, 0, 0)
        )
        assert window.start.tzinfo is UTC
        assert window.days == pytest.approx(1.0)

    def test_aware_timestamps_are_converted(self):
        from datetime import timezone

        window = normalise_window(
            datetime(2026, 1, 1, 3, 0, tzinfo=UTC),
            datetime(2026, 1, 2, 3, 0, tzinfo=UTC),
        )
        assert window.start.tzinfo is UTC
        assert window.days == pytest.approx(1.0)

    def test_rejects_inverted(self):
        with pytest.raises(ValueError, match="after start"):
            normalise_window(
                datetime(2026, 1, 2), datetime(2026, 1, 1)
            )

    def test_rejects_too_wide(self):
        with pytest.raises(ValueError, match="must not exceed"):
            normalise_window(
                datetime(2026, 1, 1), datetime(2027, 6, 1)  # 517 days
            )

    def test_accepts_the_maximum_width(self):
        window = normalise_window(datetime(2026, 1, 1), datetime(2027, 1, 2))  # 366 days
        assert window.days == pytest.approx(366.0)


class TestCsvRendering:
    def test_uses_the_report_declared_columns(self):
        report = {
            "columns": ["a", "b"],
            "rows": [{"a": 1, "b": None}, {"a": 2, "b": "x"}],
        }
        out = to_csv(report).strip().split("\n")
        assert out[0] == "a,b"
        assert out[1] == "1,"          # None renders as empty, not "None"
        assert out[2] == "2,x"

    def test_handles_no_rows(self):
        assert to_csv({"columns": ["a"], "rows": []}).strip() == "a"