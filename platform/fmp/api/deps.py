"""FastAPI dependencies: auth guards, roles, and session scoping."""
from __future__ import annotations

import uuid
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from fmp.core.database import get_session
from fmp.core.logging_setup import add_context
from fmp.core.redis import RedisClient, get_redis_client
from fmp.core.security import decode_token, token_revoked
from fmp.models import User
from fmp.services.auth import load_active_user

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    session: SessionDep,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    redis: RedisClient = Depends(get_redis_client),
) -> User:
    """FastAPI dependency: resolve the Bearer token to an active user or 401.

    The token is decoded exactly once: its ``jti`` is checked against the
    revocation denylist and its ``sub`` used to load the active user.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        claims = decode_token(credentials.credentials)
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if await token_revoked(redis, claims):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        user_id = uuid.UUID(str(claims.get("sub")))
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = await load_active_user(session, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Record the actor twice, deliberately.
    #
    # `state` is per-request and propagates back out through Starlette's
    # BaseHTTPMiddleware, so the access log can attribute the request. The
    # ContextVar covers every record emitted *inside* the request's own task.
    # Reading only the ContextVar leaves `username: null` in the access log,
    # because that middleware frame never sees the downstream write.
    add_context(username=user.username, role=user.role, company_id=str(user.company_id))
    # `state` propagates back out through Starlette's BaseHTTPMiddleware; the
    # ContextVar above does not, so the access log reads this instead.
    request.state.username = user.username
    request.state.role = user.role
    request.state.company_id = str(user.company_id) if user.company_id else None
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: str):
    """Factory for role-guarded dependencies (e.g. ``admin``, ``company_admin``)."""

    async def _guard(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {', '.join(roles)}",
            )
        return user

    return _guard


#: Mutation-capable tenant staff: admin + company_admin.
PrivilegedUser = Annotated[User, Depends(require_roles("admin", "company_admin"))]

#: Platform operator only.
AdminUser = Annotated[User, Depends(require_roles("admin"))]