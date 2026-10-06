"""Companies API: tenant registry + site listing (tenant-scoped)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from fmp.api.deps import AdminUser, CurrentUser, PrivilegedUser, SessionDep
from fmp.models import Company, Site
from fmp.schemas.org import CompanyCreate, CompanyRead, CompanyUpdate, SiteRead
from fmp.services import audit as audit_log

router = APIRouter(prefix="/api/v1/companies", tags=["companies"])


async def _get_scoped(session, company_id: uuid.UUID, caller) -> Company:
    company = (
        await session.execute(select(Company).where(Company.id == company_id))
    ).scalar_one_or_none()
    if company is None or company.deleted_at is not None:
        raise HTTPException(404, "company not found")
    if caller.role != "admin" and caller.company_id != company.id:
        raise HTTPException(404, "company not found")
    return company


@router.get("", response_model=list[CompanyRead])
async def list_companies(current: CurrentUser, session: SessionDep):
    stmt = select(Company).where(Company.deleted_at.is_(None)).order_by(Company.name)
    if current.role != "admin":
        stmt = stmt.where(Company.id == current.company_id)
    return (await session.execute(stmt)).scalars().all()


@router.post("", response_model=CompanyRead, status_code=201)
async def create_company(
    payload: CompanyCreate,
    session: SessionDep,
    current: AdminUser,
):
    dup = (
        await session.execute(select(Company).where(Company.name == payload.name))
    ).scalar_one_or_none()
    if dup is not None and dup.deleted_at is None:
        raise HTTPException(409, "company name already exists")
    company = Company(**payload.model_dump())
    session.add(company)
    audit_log.record(
        session, actor=current, action="company.create", entity_type="company",
        entity_id=company.id, company_id=None, detail={"name": company.name},
    )
    await session.commit()
    await session.refresh(company)
    return company


@router.get("/{company_id}", response_model=CompanyRead)
async def get_company(company_id: uuid.UUID, current: CurrentUser, session: SessionDep):
    return await _get_scoped(session, company_id, current)


@router.patch("/{company_id}", response_model=CompanyRead)
async def update_company(
    company_id: uuid.UUID,
    payload: CompanyUpdate,
    session: SessionDep,
    current: PrivilegedUser,
):
    company = await _get_scoped(session, company_id, current)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(company, field, value)
    audit_log.record(
        session, actor=current, action="company.update", entity_type="company",
        entity_id=company.id, company_id=company.id,
        detail={"changed": sorted(payload.model_dump(exclude_unset=True).keys())},
    )
    await session.commit()
    await session.refresh(company)
    return company


@router.delete("/{company_id}", status_code=204)
async def delete_company(
    company_id: uuid.UUID,
    session: SessionDep,
    current: AdminUser,
):
    company = await _get_scoped(session, company_id, current)
    company.soft_delete()
    audit_log.record(
        session, actor=current, action="company.delete", entity_type="company",
        entity_id=company.id, company_id=company.id,
    )
    await session.commit()


@router.post("/{company_id}/restore", response_model=CompanyRead)
async def restore_company(
    company_id: uuid.UUID,
    session: SessionDep,
    current: AdminUser,
):
    company = (
        await session.execute(select(Company).where(Company.id == company_id))
    ).scalar_one_or_none()
    if company is None:
        raise HTTPException(404, "company not found")
    company.restore()
    audit_log.record(
        session, actor=current, action="company.restore", entity_type="company",
        entity_id=company.id, company_id=company.id,
    )
    await session.commit()
    await session.refresh(company)
    return company


@router.get("/{company_id}/sites", response_model=list[SiteRead])
async def company_sites(company_id: uuid.UUID, current: CurrentUser, session: SessionDep):
    await _get_scoped(session, company_id, current)
    rows = (
        await session.execute(
            select(Site)
            .where(Site.company_id == company_id, Site.deleted_at.is_(None))
            .order_by(Site.name)
        )
    ).scalars().all()
    return rows
