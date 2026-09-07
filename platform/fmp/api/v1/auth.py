"""Authentication API: login, current user. JWT-issuing endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from fmp.api.deps import CurrentUser, SessionDep
from fmp.core.security import create_access_token
from fmp.models import User
from fmp.schemas.user import UserRead
from fmp.services.auth import authenticate

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, session: SessionDep):
    user = await authenticate(session, payload.username, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_access_token(user.id, extra={"role": user.role})
    return LoginResponse(access_token=token, user=UserRead.model_validate(user))


@router.get("/me", response_model=UserRead)
async def me(current: CurrentUser):
    return current