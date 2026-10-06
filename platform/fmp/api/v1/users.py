"""User administration API (RBAC + tenant scoped).

* Platform ``admin`` manages every user; ``company_admin`` manages users of
  their own company (and can never create or alter platform admins).
* ``user`` role has no access here.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from fmp.api.deps import PrivilegedUser, SessionDep
from fmp.models import User
from fmp.schemas.user import UserCreate, UserRead, UserSetPassword, UserUpdate
from fmp.services import audit as audit_log
from fmp.services.users import UserAdminError, create_user, set_password, update_user

router = APIRouter(prefix="/api/v1/users", tags=["users"])


def _err(exc: UserAdminError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=exc.detail)


def _check_target_scope(caller: User, target: User) -> None:
    if caller.role == "admin":
        return
    if target.company_id != caller.company_id or target.role == "admin":
        raise HTTPException(404, "user not found")


@router.get("", response_model=list[UserRead])
async def list_users(
    current: PrivilegedUser,
    session: SessionDep,
    company_id: uuid.UUID | None = Query(default=None),
    role: str | None = Query(default=None),
    include_inactive: bool = False,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    stmt = select(User).where(User.deleted_at.is_(None))
    if not include_inactive:
        stmt = stmt.where(User.is_active.is_(True))
    if current.role != "admin":
        stmt = stmt.where(User.company_id == current.company_id)
    elif company_id is not None:
        stmt = stmt.where(User.company_id == company_id)
    if role:
        stmt = stmt.where(User.role == role)
    stmt = stmt.order_by(User.username).offset(offset).limit(limit)
    return (await session.execute(stmt)).scalars().all()


@router.post("", response_model=UserRead, status_code=201)
async def create_user_endpoint(
    payload: UserCreate,
    current: PrivilegedUser,
    session: SessionDep,
):
    try:
        user = await create_user(session, current, payload)
    except UserAdminError as exc:
        raise _err(exc) from exc
    audit_log.record(
        session, actor=current, action="user.create", entity_type="user",
        entity_id=user.id, company_id=user.company_id,
        detail={"username": user.username, "role": user.role},
    )
    await session.commit()
    await session.refresh(user)
    return user


@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: uuid.UUID,
    current: PrivilegedUser,
    session: SessionDep,
):
    target = await session.get(User, user_id)
    if target is None or target.deleted_at is not None:
        raise HTTPException(404, "user not found")
    _check_target_scope(current, target)
    return target


@router.patch("/{user_id}", response_model=UserRead)
async def patch_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    current: PrivilegedUser,
    session: SessionDep,
):
    target = await session.get(User, user_id)
    if target is None or target.deleted_at is not None:
        raise HTTPException(404, "user not found")
    _check_target_scope(current, target)
    try:
        await update_user(session, current, target, payload)
    except UserAdminError as exc:
        raise _err(exc) from exc
    audit_log.record(
        session, actor=current, action="user.update", entity_type="user",
        entity_id=target.id, company_id=target.company_id,
        detail={"changed": sorted(payload.model_dump(exclude_unset=True).keys())},
    )
    await session.commit()
    await session.refresh(target)
    return target


@router.post("/{user_id}/set-password", status_code=204)
async def admin_set_password(
    user_id: uuid.UUID,
    payload: UserSetPassword,
    current: PrivilegedUser,
    session: SessionDep,
):
    target = await session.get(User, user_id)
    if target is None or target.deleted_at is not None:
        raise HTTPException(404, "user not found")
    _check_target_scope(current, target)
    try:
        await set_password(session, current, target, payload.new_password)
    except UserAdminError as exc:
        raise _err(exc) from exc
    audit_log.record(
        session, actor=current, action="user.set_password", entity_type="user",
        entity_id=target.id, company_id=target.company_id,
    )
    await session.commit()


@router.post("/{user_id}/deactivate", response_model=UserRead)
async def deactivate_user(
    user_id: uuid.UUID,
    current: PrivilegedUser,
    session: SessionDep,
):
    target = await session.get(User, user_id)
    if target is None or target.deleted_at is not None:
        raise HTTPException(404, "user not found")
    _check_target_scope(current, target)
    try:
        await update_user(session, current, target, UserUpdate(is_active=False))
    except UserAdminError as exc:
        raise _err(exc) from exc
    audit_log.record(
        session, actor=current, action="user.deactivate", entity_type="user",
        entity_id=target.id, company_id=target.company_id,
    )
    await session.commit()
    await session.refresh(target)
    return target


@router.post("/{user_id}/restore", response_model=UserRead)
async def restore_user(
    user_id: uuid.UUID,
    current: PrivilegedUser,
    session: SessionDep,
):
    target = await session.get(User, user_id)
    if target is None or target.deleted_at is not None:
        raise HTTPException(404, "user not found")
    _check_target_scope(current, target)
    try:
        await update_user(session, current, target, UserUpdate(is_active=True))
    except UserAdminError as exc:
        raise _err(exc) from exc
    audit_log.record(
        session, actor=current, action="user.restore", entity_type="user",
        entity_id=target.id, company_id=target.company_id,
    )
    await session.commit()
    await session.refresh(target)
    return target
