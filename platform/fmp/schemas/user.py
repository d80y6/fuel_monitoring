"""User API schemas (Pydantic v2)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    email: str
    first_name: str | None = None
    last_name: str | None = None
    role: str
    is_active: bool
    phone: str | None = None
    last_login: datetime | None = None
    created_at: datetime