"""Integration tests for dispensers PATCH endpoint."""
from __future__ import annotations

import pytest
import httpx

pytestmark = pytest.mark.asyncio


async def test_dispensers_patch(client: httpx.AsyncClient) -> None:
    # GET stations to find a station_id
    r = await client.get("/api/v1/stations")
    assert r.status_code == 200
    stations = r.json()
    station_id = stations[0]["id"]

    # GET dispensers to find a dispenser_id
    r = await client.get(f"/api/v1/stations/{station_id}/dispensers")
    assert r.status_code == 200
    dispensers = r.json()
    dispenser_id = dispensers[0]["id"]

    # PATCH to toggle is_active
    r = await client.patch(
        f"/api/v1/stations/{station_id}/dispensers/{dispenser_id}",
        json={"is_active": False},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["is_active"] is False

    # PATCH to update name
    r = await client.patch(
        f"/api/v1/stations/{station_id}/dispensers/{dispenser_id}",
        json={"name": "Pump Updated"},
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Pump Updated"


async def test_dispensers_patch_not_found(client: httpx.AsyncClient) -> None:
    r = await client.patch(
        "/api/v1/stations/nonexistent/dispensers/nonexistent",
        json={"is_active": False},
    )
    assert r.status_code in (404, 422)


async def test_dispensers_patch_empty_body(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/v1/stations")
    stations = r.json()
    station_id = stations[0]["id"]
    r = await client.get(f"/api/v1/stations/{station_id}/dispensers")
    dispensers = r.json()
    dispenser_id = dispensers[0]["id"]

    r = await client.patch(
        f"/api/v1/stations/{station_id}/dispensers/{dispenser_id}",
        json={},
    )
    # Should either succeed with no change or return 422
    assert r.status_code in (200, 422)
