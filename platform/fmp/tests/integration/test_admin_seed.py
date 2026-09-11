"""Integration tests for the admin-user seed script."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from fmp.core.config import settings
from fmp.core.security import hash_password, verify_password
from fmp.models.user import User

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _patch_admin_defaults(monkeypatch):
    """Reset admin seed env for every test so tests are hermetic."""
    monkeypatch.setattr(settings, "ADMIN_USERNAME", "admin")
    monkeypatch.setattr(settings, "ADMIN_EMAIL", "admin@fuelplatform.local")
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "Admin@1234")
    monkeypatch.setattr(settings, "ADMIN_FORCE_PASSWORD", False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _get_admin(session) -> User | None:
    stmt = select(User).where(User.username == settings.ADMIN_USERNAME)
    return (await session.execute(stmt)).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
async def test_seed_creates_admin(db):
    from fmp.core.database import async_session_factory
    from fmp.scripts.seed_admin import seed_admin

    outcome = await seed_admin()
    assert outcome == "created"

    async with async_session_factory() as session:
        user = await _get_admin(session)
        assert user is not None
        assert user.username == "admin"
        assert user.role == "admin"
        assert user.is_active is True
        assert user.email == "admin@fuelplatform.local"
        assert verify_password("Admin@1234", user.password_hash)


async def test_seed_idempotent(db):
    from fmp.core.database import async_session_factory
    from fmp.scripts.seed_admin import seed_admin

    # First run creates
    assert await seed_admin() == "created"

    # Tamper with the user to prove second run doesn't touch it
    async with async_session_factory() as session:
        user = await _get_admin(session)
        # Simulate user changing their password externally
        user.password_hash = hash_password("ExternallyChanged!X9")
        await session.commit()
        tampered_hash = user.password_hash

    # Second run without force → "exists", hash unchanged
    assert await seed_admin() == "exists"

    async with async_session_factory() as session:
        user = await _get_admin(session)
        assert user.password_hash == tampered_hash  # external change preserved


async def test_seed_force_password_resets(db):
    from fmp.core.database import async_session_factory
    from fmp.scripts.seed_admin import seed_admin

    # First run creates
    assert await seed_admin() == "created"

    async with async_session_factory() as session:
        user = await _get_admin(session)
        original_hash = user.password_hash

    # Enable force
    settings.ADMIN_FORCE_PASSWORD = True  # type: ignore[attr-defined]
    try:
        outcome = await seed_admin()
        assert outcome == "reset"

        async with async_session_factory() as session:
            user = await _get_admin(session)
            assert user.password_hash != original_hash
            # The default password should still work
            assert verify_password("Admin@1234", user.password_hash)
            assert user.is_active is True
    finally:
        settings.ADMIN_FORCE_PASSWORD = False  # type: ignore[attr-defined]


async def test_seed_refuses_weak_password(monkeypatch):
    from fmp.scripts.seed_admin import seed_admin

    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "weak")
    with pytest.raises(RuntimeError):
        await seed_admin()


async def test_seed_empty_password_raises():
    from fmp.scripts.seed_admin import seed_admin

    settings.ADMIN_PASSWORD = ""  # type: ignore[attr-defined]
    try:
        with pytest.raises(RuntimeError):
            await seed_admin()
    finally:
        settings.ADMIN_PASSWORD = "Admin@1234"  # type: ignore[attr-defined]
