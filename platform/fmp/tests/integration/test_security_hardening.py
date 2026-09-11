"""Integration tests: login rate limiting (C1) + change-password flow (H4).

Rate limiting is exercised against the REAL Redis (``REDIS_PORT=6479`` in the
test env) using unique usernames per test so keys never collide across tests
or runs. ``LOGIN_RATE_LIMIT_ENABLED`` stays at its default ``True``.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio


async def _seed_user(username: str, password: str = "OldPassw0rd!"):
    from fmp.core.database import async_session_factory
    from fmp.core.security import hash_password
    from fmp.models import User

    async with async_session_factory() as session:
        user = User(
            username=username,
            email=f"{username}@t.io",
            password_hash=hash_password(password),
            role="user",
            is_active=True,
        )
        session.add(user)
        await session.commit()
        return user


async def _login(client: AsyncClient, username: str, password: str):
    return await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )


async def _token_for(client: AsyncClient, username: str, password: str) -> str:
    r = await _login(client, username, password)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def test_login_rate_limit_blocks_after_5_failures(db):
    from fmp.api.main import app

    username = f"rl_{uuid.uuid4().hex[:10]}"
    await _seed_user(username, "RightPass1!")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for _ in range(5):
            r = await _login(client, username, "WrongPass")
            assert r.status_code == 401, r.text
            assert "X-RateLimit-Remaining" in r.headers

        r6 = await _login(client, username, "WrongPass")
        assert r6.status_code == 429, r6.text
        assert "X-RateLimit-Remaining" in r6.headers


async def test_login_rate_limit_not_consumed_on_success(db):
    from fmp.api.main import app

    username = f"rls_{uuid.uuid4().hex[:10]}"
    await _seed_user(username, "RightPass1!")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 3 failures ...
        for _ in range(3):
            assert (await _login(client, username, "WrongPass")).status_code == 401
        # ... then a success must NOT consume a slot ...
        assert (await _login(client, username, "RightPass1!")).status_code == 200
        # ... so two more failures are still 401, and only the 6th is blocked.
        for _ in range(2):
            assert (await _login(client, username, "WrongPass")).status_code == 401
        assert (await _login(client, username, "WrongPass")).status_code == 429


async def test_change_password_happy_path(db):
    from fmp.api.main import app

    username = f"cp_{uuid.uuid4().hex[:10]}"
    await _seed_user(username, "OldPassw0rd!")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _token_for(client, username, "OldPassw0rd!")
        headers = {"Authorization": f"Bearer {token}"}

        r = await client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "OldPassw0rd!", "new_password": "NewPassw0rd!"},
            headers=headers,
        )
        assert r.status_code == 200, r.text
        assert r.json() == {"status": "ok"}

        # old password no longer works
        assert (await _login(client, username, "OldPassw0rd!")).status_code == 401
        # new password works
        assert (await _login(client, username, "NewPassw0rd!")).status_code == 200


async def test_change_password_wrong_current_rejected(db):
    from fmp.api.main import app

    username = f"cpw_{uuid.uuid4().hex[:10]}"
    await _seed_user(username, "OldPassw0rd!")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _token_for(client, username, "OldPassw0rd!")
        r = await client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "WrongCurrent1!", "new_password": "NewPassw0rd!"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 401, r.text
        assert "Incorrect current password" in r.text


async def test_change_password_weak_new_rejected(db):
    from fmp.api.main import app

    username = f"cpw2_{uuid.uuid4().hex[:10]}"
    await _seed_user(username, "OldPassw0rd!")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _token_for(client, username, "OldPassw0rd!")
        r = await client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "OldPassw0rd!", "new_password": "weak"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 422, r.text
        assert "must be at least 8 characters" in r.text