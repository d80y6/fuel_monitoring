"""FastAPI dependencies: auth guards, roles, and session scoping."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from fmp.core.database import get_session
from fmp.models import User
from fmp.services.auth import load_user_for_token

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    session: SessionDep,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> User:
    """FastAPI dependency: resolve the Bearer token to an active user or 401."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = await load_user_for_token(session, credentials.credentials)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
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


#: Mutation-capable staff: admin + company_admin.
PrivilegedUser = Annotated[User, Depends(require_roles("admin", "company_admin"))]