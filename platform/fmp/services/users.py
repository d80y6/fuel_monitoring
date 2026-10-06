"""User directory service: create/update/deactivate under RBAC + tenancy rules.

Rules
-----
* ``admin`` (platform) may create/change any user, including other admins.
* ``company_admin`` may manage users *inside their own company only*, and may
  only assign roles ``company_admin`` | ``user``.
* A non-admin user must always carry a ``company_id``.
* Deactivation is soft (``is_active=False``) so audit history survives.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fmp.core.security import hash_password, validate_password_complexity
from fmp.models import Company, User
from fmp.schemas.user import UserCreate, UserUpdate


class UserAdminError(Exception):
    """Carries an HTTP-appropriate (status, detail) payload."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _check_role_assignment(actor: User, role: str) -> None:
    if actor.role != "admin" and role == "admin":
        raise UserAdminError(403, "only platform admin may create admin accounts")


def _resolve_company(actor: User, company_id: uuid.UUID | None, role: str) -> uuid.UUID | None:
    if role == "admin":
        return None if actor.role == "admin" else actor.company_id
    if actor.role == "admin":
        if company_id is None:
            raise UserAdminError(422, "company_id is required for non-admin users")
        return company_id
    # tenant admin manages only their own company
    return actor.company_id


async def _validate_company(session: AsyncSession, company_id: uuid.UUID | None) -> None:
    if company_id is None:
        return
    company = await session.get(Company, company_id)
    if company is None or company.deleted_at is not None:
        raise UserAdminError(404, "company not found")


async def create_user(session: AsyncSession, actor: User, payload: UserCreate) -> User:
    _check_role_assignment(actor, payload.role)
    company_id = _resolve_company(actor, payload.company_id, payload.role)
    await _validate_company(session, company_id)

    violations = validate_password_complexity(payload.password)
    if violations:
        raise UserAdminError(422, "; ".join(violations))

    for field, value in (("username", payload.username), ("email", payload.email)):
        taken = (
            await session.execute(
                select(User).where(getattr(User, field) == value)
            )
        ).scalar_one_or_none()
        if taken is not None:
            raise UserAdminError(409, f"{field} already registered")

    user = User(
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
        first_name=payload.first_name,
        last_name=payload.last_name,
        role=payload.role,
        company_id=company_id,
        phone=payload.phone,
        is_active=True,
    )
    session.add(user)
    await session.flush()
    return user


async def update_user(session: AsyncSession, actor: User, target: User, payload: UserUpdate) -> User:
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        return target

    if "role" in fields and fields["role"] is not None:
        _check_role_assignment(actor, fields["role"])
    if "company_id" in fields:
        if actor.role != "admin" and fields["company_id"] != actor.company_id:
            raise UserAdminError(403, "cannot move a user outside your company")
        await _validate_company(session, fields["company_id"])
    if actor.role != "admin" and target.company_id != actor.company_id:
        raise UserAdminError(403, "user belongs to a different company")
    if target.id == actor.id and fields.get("is_active") is False:
        raise UserAdminError(400, "cannot deactivate your own account")
    if target.role == "admin" and actor.role != "admin":
        raise UserAdminError(403, "cannot modify a platform admin")

    effective_role = fields.get("role", target.role)
    effective_company = fields.get("company_id", target.company_id)
    if effective_role != "admin" and effective_company is None:
        raise UserAdminError(422, "non-admin users must have a company_id")

    for key, value in fields.items():
        setattr(target, key, value)
    await session.flush()
    return target


async def set_password(session: AsyncSession, actor: User, target: User, new_password: str) -> None:
    if actor.role != "admin" and target.company_id != actor.company_id:
        raise UserAdminError(403, "user belongs to a different company")
    violations = validate_password_complexity(new_password)
    if violations:
        raise UserAdminError(422, "; ".join(violations))
    target.password_hash = hash_password(new_password)
    await session.flush()
