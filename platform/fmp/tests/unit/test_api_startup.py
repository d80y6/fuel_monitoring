"""Liveness stays dependency-free (audit G-201).

The orchestrator must not restart a healthy API because the database is down:
liveness answers "is this process working", readiness answers "can it serve".
Collapsing them is how a database blip turns into an outage.
"""
import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def http():
    """Async ASGI client.

    The rest of the suite uses this rather than the sync TestClient, which
    starlette now deprecates (it pulls in httpx 0.x semantics). Keeping one
    client style avoids a permanent third-party DeprecationWarning.
    """
    from fmp.api.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_api_starts_and_serves_health(http):
    response = await http.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "api"
    assert "time" in body


async def test_health_echoes_a_request_id(http):
    """An inbound correlation id is honoured, not replaced."""
    response = await http.get("/api/v1/health", headers={"X-Request-ID": "abc123"})

    assert response.headers["X-Request-ID"] == "abc123"


async def test_health_mints_a_request_id_when_none_is_supplied(http):
    response = await http.get("/api/v1/health")

    assert response.headers.get("X-Request-ID")


async def test_health_brief_is_public_and_coarse():
    """Uptime checks must not need a token, and must not leak fleet topology.

    The database is stubbed because a *unit* test must not require the
    infrastructure this endpoint is meant to report on; the integration suite
    exercises it against a real database.
    """
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch

    # scalar_one() is awaited by the endpoint, so the mock must return the
    # value directly rather than another coroutine.
    fake_result = SimpleNamespace(scalar_one=lambda: None)
    fake_session = AsyncMock()
    fake_session.execute = AsyncMock(return_value=fake_result)
    session_ctx = AsyncMock()
    session_ctx.__aenter__.return_value = fake_session
    session_ctx.__aexit__.return_value = False

    from fmp.api.main import app

    with patch("fmp.core.database.async_session_factory", return_value=session_ctx):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/metrics/health-brief")

    assert response.status_code == 200
    body = response.json()
    assert "telemetry_receiving" in body
    assert "tanks_offline" in body
    # No tank/site/company identifiers in the public payload.
    assert "tanks" not in body
    assert "sites" not in body


async def test_metrics_requires_authentication(http):
    """Detailed metrics expose fleet topology and must stay admin-only."""
    response = await http.get("/api/v1/metrics")

    assert response.status_code in (401, 403)


async def test_security_headers_are_present(http):
    response = await http.get("/api/v1/health")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


async def test_api_responses_are_not_cached(http):
    """Operator data must never be served from a shared cache."""
    response = await http.get("/api/v1/tanks")

    assert response.headers.get("Cache-Control") == "no-store"