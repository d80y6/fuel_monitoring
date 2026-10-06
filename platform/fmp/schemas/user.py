"""User API schemas (Pydantic v2)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

#: Valid roles; enforced by the service layer (never trust the client).
ROLES = ("admin", "company_admin", "user")


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    email: str
    first_name: str | None = None
    last_name: str | None = None
    role: str
    company_id: uuid.UUID | None = None
    is_active: bool
    phone: str | None = None
    last_login: datetime | None = None
    created_at: datetime


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.\-]+$")
    email: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=1, max_length=128)
    first_name: str | None = Field(default=None, max_length=64)
    last_name: str | None = Field(default=None, max_length=64)
    role: str = Field(default="user", pattern="^(admin|company_admin|user)$")
    # Required unless role == "admin" (platform operator). Tenant users must be
    # bound to exactly one company — enforced in the service layer.
    company_id: uuid.UUID | None = None
    phone: str | None = Field(default=None, max_length=20)


class UserUpdate(BaseModel):
    email: str | None = Field(default=None, min_length=3, max_length=120)
    first_name: str | None = Field(default=None, max_length=64)
    last_name: str | None = Field(default=None, max_length=64)
    role: str | None = Field(default=None, pattern="^(admin|company_admin|user)$")
    company_id: uuid.UUID | None = None
    phone: str | None = Field(default=None, max_length=20)
    is_active: bool | None = None


class UserSetPassword(BaseModel):
    new_password: str = Field(min_length=1, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=1)


class ChangePasswordResponse(BaseModel):
    status: str
