"""Authentication service: credential verification + JWT issuance."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from fmp.core.security import (
    create_access_token,
    decode_token,
    verify_password,
)
from fmp.models import User


def issue_token_for_user(user: User) -> str:
    """Mint an access token carrying the user's role for RBAC checks."""
    return create_access_token(user.id, extra={"role": user.role})


def token_role(token: str) -> str | None:
    try:
        return decode_token(token).get("role")
    except Exception:
        return None


async def authenticate(session, username: str, password: str) -> User | None:
    """Return the authenticated user or ``None`` (constant-time on failure)."""
    user = (
        await session.execute(
            select(User).where(
                User.username == username,
                User.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()

    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None

    user.last_login = datetime.now(timezone.utc)
    await session.commit()
    return user


async def load_user_for_token(session, token: str) -> User | None:
    """Resolve a JWT subject back to an active user (for the Bearer dependency)."""
    try:
        claims = decode_token(token)
    except Exception:
        return None

    try:
        user_id = uuid.UUID(str(claims.get("sub")))
    except (ValueError, TypeError):
        return None

    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None or not user.is_active or user.deleted_at is not None:
        return None
    return user