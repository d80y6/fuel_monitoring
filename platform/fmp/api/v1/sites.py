"""Sites API: CRUD + nested stations (tenant-scoped)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from fmp.api.deps import CurrentUser, PrivilegedUser, SessionDep
from fmp.models import Site, Station
from fmp.schemas.org import SiteCreate, SiteRead, SiteUpdate, StationRead
from fmp.services import audit as audit_log

router = APIRouter(prefix="/api/v1/sites", tags=["sites"])


async def _get_scoped(session, site_id: uuid.UUID, caller) -> Site:
    site = (
        await session.execute(select(Site).where(Site.id == site_id))
    ).scalar_one_or_none()
    if site is None or site.deleted_at is not None:
        raise HTTPException(404, "site not found")
    if caller.role != "admin" and site.company_id != caller.company_id:
        raise HTTPException(404, "site not found")
    return site


@router.get("", response_model=list[SiteRead])
async def list_sites(
    current: CurrentUser,
    session: SessionDep,
    company_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    stmt = select(Site).where(Site.deleted_at.is_(None))
    if current.role != "admin":
        stmt = stmt.where(Site.company_id == current.company_id)
    elif company_id is not None:
        stmt = stmt.where(Site.company_id == company_id)
    rows = (
        await session.execute(stmt.order_by(Site.name).offset(offset).limit(limit))
    ).scalars().all()
    return rows


@router.post("", response_model=SiteRead, status_code=201)
async def create_site(payload: SiteCreate, current: PrivilegedUser, session: SessionDep):
    if current.role != "admin" and payload.company_id != current.company_id:
        raise HTTPException(404, "company not found")
    site = Site(**payload.model_dump())
    session.add(site)
    audit_log.record(
        session, actor=current, action="site.create", entity_type="site",
        company_id=site.company_id, detail={"name": site.name},
    )
    await session.commit()
    await session.refresh(site)
    return site


@router.get("/{site_id}", response_model=SiteRead)
async def get_site(site_id: uuid.UUID, current: CurrentUser, session: SessionDep):
    return await _get_scoped(session, site_id, current)


@router.patch("/{site_id}", response_model=SiteRead)
async def update_site(
    site_id: uuid.UUID, payload: SiteUpdate, current: PrivilegedUser, session: SessionDep
):
    site = await _get_scoped(session, site_id, current)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(site, field, value)
    audit_log.record(
        session, actor=current, action="site.update", entity_type="site",
        entity_id=site.id, company_id=site.company_id, detail={"changed": sorted(changes)},
    )
    await session.commit()
    await session.refresh(site)
    return site


@router.delete("/{site_id}", status_code=204)
async def delete_site(site_id: uuid.UUID, current: PrivilegedUser, session: SessionDep):
    site = await _get_scoped(session, site_id, current)
    site.soft_delete()
    audit_log.record(
        session, actor=current, action="site.delete", entity_type="site",
        entity_id=site.id, company_id=site.company_id,
    )
    await session.commit()


@router.post("/{site_id}/restore", response_model=SiteRead)
async def restore_site(site_id: uuid.UUID, current: PrivilegedUser, session: SessionDep):
    site = (
        await session.execute(select(Site).where(Site.id == site_id))
    ).scalar_one_or_none()
    if site is None:
        raise HTTPException(404, "site not found")
    if current.role != "admin" and site.company_id != current.company_id:
        raise HTTPException(404, "site not found")
    site.restore()
    audit_log.record(
        session, actor=current, action="site.restore", entity_type="site",
        entity_id=site.id, company_id=site.company_id,
    )
    await session.commit()
    await session.refresh(site)
    return site


@router.get("/{site_id}/stations", response_model=list[StationRead])
async def site_stations(site_id: uuid.UUID, current: CurrentUser, session: SessionDep):
    await _get_scoped(session, site_id, current)
    rows = (
        await session.execute(
            select(Station)
            .where(Station.site_id == site_id, Station.deleted_at.is_(None))
            .order_by(Station.name)
        )
    ).scalars().all()
    return rows
