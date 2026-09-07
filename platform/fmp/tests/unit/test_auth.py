"""Unit tests for the auth service (authenticate + token issuance)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from fmp.core.security import create_access_token, hash_password
from fmp.models.user import User
from fmp.services.auth import (
    authenticate,
    issue_token_for_user,
    load_user_for_token,
)


class StubResult:
    def __init__(self, obj):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj


class StubSession:
    def __init__(self, user):
        self._user = user

    async def execute(self, stmt):
        return StubResult(self._user)

    async def commit(self):
        return None


def _user(**overrides):
    defaults = dict(
        id=uuid.uuid4(),
        username="admin",
        email="admin@test.io",
        password_hash=hash_password("RightPass123"),
        role="admin",
        is_active=True,
    )
    defaults.update(overrides)
    return User(**defaults)


@pytest.mark.asyncio
async def test_authenticate_returns_user_on_valid_credentials():
    user = _user()
    result = await authenticate(StubSession(user), "admin", "RightPass123")
    assert result is user


@pytest.mark.asyncio
async def test_authenticate_rejects_wrong_password():
    user = _user()
    result = await authenticate(StubSession(user), "admin", "WrongPass123")
    assert result is None


@pytest.mark.asyncio
async def test_authenticate_rejects_inactive_user():
    user = _user(is_active=False)
    result = await authenticate(StubSession(user), "admin", "RightPass123")
    assert result is None


@pytest.mark.asyncio
async def test_authenticate_returns_none_when_user_missing():
    result = await authenticate(StubSession(None), "nobody", "Whatever123")
    assert result is None


def test_issue_token_contains_role_claim():
    user = _user()
    token = issue_token_for_user(user)
    assert token
    from fmp.core.security import decode_token

    claims = decode_token(token)
    assert claims["sub"] == str(user.id)
    assert claims["role"] == "admin"


@pytest.mark.asyncio
async def test_load_user_for_token_roundtrip():
    user = _user(last_login=datetime.now(timezone.utc))
    token = issue_token_for_user(user)
    loaded = await load_user_for_token(StubSession(user), token)
    assert loaded is user


@pytest.mark.asyncio
async def test_load_user_for_token_rejects_inactive():
    user = _user(is_active=False)
    token = issue_token_for_user(user)
    assert await load_user_for_token(StubSession(user), token) is None


@pytest.mark.asyncio
async def test_load_user_for_token_rejects_garbage():
    assert await load_user_for_token(StubSession(None), "garbage.token") is None