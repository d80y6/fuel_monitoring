"""Authentication API: login, current user, change-password. JWT-issuing endpoints."""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from fmp.api.deps import CurrentUser, SessionDep
from fmp.core.config import get_settings
from fmp.core.redis import RedisClient, get_redis_client
from fmp.core.security import (
    create_access_token,
    hash_password,
    validate_password_complexity,
    verify_password,
)
from fmp.models import User
from fmp.schemas.user import ChangePasswordRequest, ChangePasswordResponse, UserRead
from fmp.services.auth import authenticate

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

settings = get_settings()

#: Bounded in-process fallback for login rate limiting when Redis is down.
_LOGIN_FALLBACK_MAX_KEYS = 10_000
_fallback_attempts: dict[str, list[float]] = {}


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


def _login_rate_key(username: str, client_ip: str) -> str:
    return f"ratelimit:login:{username}:{client_ip}"


def _fallback_consume(key: str) -> tuple[bool, int]:
    """In-process mirror of ``RedisClient.rate_limit`` semantics.

    Returns ``(allowed, remaining_before_increment)``; expired timestamps are
    evicted on access and the oldest keys are dropped once the dict exceeds
    the cap, so the fallback stays bounded (~memory-safe under abuse).
    """
    now = time.time()
    window_start = now - settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS
    entries = [ts for ts in _fallback_attempts.get(key, []) if ts > window_start]
    if len(entries) >= settings.LOGIN_RATE_LIMIT_ATTEMPTS:
        _fallback_attempts[key] = entries
        return False, 0
    entries.append(now)
    _fallback_attempts[key] = entries
    while len(_fallback_attempts) > _LOGIN_FALLBACK_MAX_KEYS:
        _fallback_attempts.pop(next(iter(_fallback_attempts)))
    return True, settings.LOGIN_RATE_LIMIT_ATTEMPTS - len(entries)


async def login_rate_limited(redis: RedisClient, username: str, client_ip: str) -> tuple[bool, int]:
    """Record one failed login attempt; return ``(allowed, remaining_before_increment)``.

    Uses Redis when available; falls back to an in-process bounded dict when
    Redis is unavailable so an outage NEVER fails open to unlimited attempts.

    Note: ``client_ip`` is the peer address from ASGI (``request.client.host``).
    ``X-Forwarded-For`` is intentionally NOT trusted here — it is spoofable and
    would let an attacker rotate the header to bypass the limit.
    """
    if not settings.LOGIN_RATE_LIMIT_ENABLED:
        return True, settings.LOGIN_RATE_LIMIT_ATTEMPTS
    key = _login_rate_key(username, client_ip)
    try:
        return await redis.rate_limit(
            key,
            settings.LOGIN_RATE_LIMIT_ATTEMPTS,
            settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS,
        )
    except Exception:
        return _fallback_consume(key)


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    session: SessionDep,
    request: Request,
    redis: RedisClient = Depends(get_redis_client),
):
    client_ip = request.client.host if request.client else "unknown"

    # Authenticate first; on failure consume one rate-limit slot. Blocking
    # happens after the limit is reached: the 429 path never writes to the DB
    # (authenticate only commits on success) and never even reaches it for
    # already-blocked clients once we short-circuit on the consume result.
    user = await authenticate(session, payload.username, payload.password)
    if user is None:
        allowed, remaining = await login_rate_limited(redis, payload.username, client_ip)
        headers = {"X-RateLimit-Remaining": str(max(0, remaining))}
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="Too many login attempts. Try again later.",
                headers=headers,
            )
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
            headers=headers,
        )
    token = create_access_token(user.id, extra={"role": user.role})
    return LoginResponse(access_token=token, user=UserRead.model_validate(user))


@router.get("/me", response_model=UserRead)
async def me(current: CurrentUser):
    return current


@router.post("/change-password", response_model=ChangePasswordResponse)
async def change_password(
    payload: ChangePasswordRequest,
    current: CurrentUser,
    session: SessionDep,
):
    """Change the authenticated user's password.

    Note: JWTs are stateless and cannot be revoked without a denylist; tokens
    minted before the change remain valid until they expire. A token denylist
    is out of scope for this hardening pass.
    """
    if not verify_password(payload.current_password, current.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect current password")
    violations = validate_password_complexity(payload.new_password)
    if violations:
        raise HTTPException(status_code=422, detail="; ".join(violations))
    current.password_hash = hash_password(payload.new_password)
    await session.commit()
    return ChangePasswordResponse(status="ok")