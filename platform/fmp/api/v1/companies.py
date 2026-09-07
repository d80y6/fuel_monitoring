"""Companies API: registry + soft-delete + site listing."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from fmp.api.deps import CurrentUser, PrivilegedUser, SessionDep
from fmp.models import Company, Site
from fmp.schemas.org import CompanyCreate, CompanyRead, CompanyUpdate, SiteRead

router = APIRouter(prefix="/api/v1/companies", tags=["companies"])


@router.get("", response_model=list[CompanyRead])
async def list_companies(_: CurrentUser, session: SessionDep):
    rows = (
        await session.execute(
            select(Company).where(Company.deleted_at.is_(None)).order_by(Company.name)
        )
    ).scalars().all()
    return rows


@router.post("", response_model=CompanyRead, status_code=201)
async def create_company(payload: CompanyCreate, _: PrivilegedUser, session: SessionDep):
    dup = (
        await session.execute(select(Company).where(Company.name == payload.name))
    ).scalar_one_or_none()
    if dup is not None and dup.deleted_at is None:
        raise HTTPException(409, "company name already exists")
    company = Company(**payload.model_dump())
    session.add(company)
    await session.commit()
    await session.refresh(company)
    return company


@router.get("/{company_id}", response_model=CompanyRead)
async def get_company(company_id: uuid.UUID, _: CurrentUser, session: SessionDep):
    company = (
        await session.execute(select(Company).where(Company.id == company_id))
    ).scalar_one_or_none()
    if company is None or company.deleted_at is not None:
        raise HTTPException(404, "company not found")
    return company


@router.patch("/{company_id}", response_model=CompanyRead)
async def update_company(
    company_id: uuid.UUID, payload: CompanyUpdate, _: PrivilegedUser, session: SessionDep
):
    company = (
        await session.execute(select(Company).where(Company.id == company_id))
    ).scalar_one_or_none()
    if company is None or company.deleted_at is not None:
        raise HTTPException(404, "company not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(company, field, value)
    await session.commit()
    await session.refresh(company)
    return company


@router.delete("/{company_id}", status_code=204)
async def delete_company(company_id: uuid.UUID, _: PrivilegedUser, session: SessionDep):
    company = (
        await session.execute(select(Company).where(Company.id == company_id))
    ).scalar_one_or_none()
    if company is None or company.deleted_at is not None:
        raise HTTPException(404, "company not found")
    company.soft_delete()
    await session.commit()


@router.get("/{company_id}/sites", response_model=list[SiteRead])
async def company_sites(company_id: uuid.UUID, _: CurrentUser, session: SessionDep):
    rows = (
        await session.execute(
            select(Site)
            .where(Site.company_id == company_id, Site.deleted_at.is_(None))
            .order_by(Site.name)
        )
    ).scalars().all()
    return rows