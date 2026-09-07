"""Sites API: CRUD + nested stations."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from fmp.api.deps import CurrentUser, SessionDep
from fmp.models import Site, Station
from fmp.schemas.org import SiteCreate, SiteRead, SiteUpdate, StationRead

router = APIRouter(prefix="/api/v1/sites", tags=["sites"])


@router.get("", response_model=list[SiteRead])
async def list_sites(_: CurrentUser, session: SessionDep):
    rows = (
        await session.execute(
            select(Site).where(Site.deleted_at.is_(None)).order_by(Site.name)
        )
    ).scalars().all()
    return rows


@router.post("", response_model=SiteRead, status_code=201)
async def create_site(payload: SiteCreate, _: CurrentUser, session: SessionDep):
    site = Site(**payload.model_dump())
    session.add(site)
    await session.commit()
    await session.refresh(site)
    return site


@router.get("/{site_id}", response_model=SiteRead)
async def get_site(site_id: uuid.UUID, _: CurrentUser, session: SessionDep):
    site = (
        await session.execute(select(Site).where(Site.id == site_id))
    ).scalar_one_or_none()
    if site is None or site.deleted_at is not None:
        raise HTTPException(404, "site not found")
    return site


@router.patch("/{site_id}", response_model=SiteRead)
async def update_site(
    site_id: uuid.UUID, payload: SiteUpdate, _: CurrentUser, session: SessionDep
):
    site = (
        await session.execute(select(Site).where(Site.id == site_id))
    ).scalar_one_or_none()
    if site is None or site.deleted_at is not None:
        raise HTTPException(404, "site not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(site, field, value)
    await session.commit()
    await session.refresh(site)
    return site


@router.delete("/{site_id}", status_code=204)
async def delete_site(site_id: uuid.UUID, _: CurrentUser, session: SessionDep):
    site = (
        await session.execute(select(Site).where(Site.id == site_id))
    ).scalar_one_or_none()
    if site is None or site.deleted_at is not None:
        raise HTTPException(404, "site not found")
    site.soft_delete()
    await session.commit()


@router.get("/{site_id}/stations", response_model=list[StationRead])
async def site_stations(site_id: uuid.UUID, _: CurrentUser, session: SessionDep):
    rows = (
        await session.execute(
            select(Station)
            .where(Station.site_id == site_id, Station.deleted_at.is_(None))
            .order_by(Station.name)
        )
    ).scalars().all()
    return rows