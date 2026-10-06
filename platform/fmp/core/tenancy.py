"""Tenant scoping primitives.

The platform is multi-tenant: every operational entity resolves to exactly one
``companies`` row (site.company_id, station→site, tank→site, allocation,
employee...). Users carry ``company_id``; platform ``admin`` accounts have
``company_id IS NULL`` and see everything, tenant accounts are restricted to
their own company.

All authorization-relevant filtering MUST go through these helpers so the
scoping rule lives in exactly one place.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import Select

from fmp.models import Site, Station, Tank, User


@dataclass(frozen=True)
class TenantScope:
    """Resolved visibility scope for one authenticated user."""

    company_id: uuid.UUID | None
    role: str

    @property
    def is_platform(self) -> bool:
        """Platform operators (admin, no company) see all tenants."""
        return self.role == "admin" and self.company_id is None


def tenant_scope(user: User) -> TenantScope:
    return TenantScope(company_id=user.company_id, role=user.role)


def require_company(user: User) -> uuid.UUID:
    """Tenant-scoped callers MUST carry a company. Raises 403-equivalent."""
    from fastapi import HTTPException

    if user.role == "admin" and user.company_id is None:
        # platform admin: caller must explicitly say which company they act on
        raise HTTPException(
            status_code=400,
            detail="platform admin must specify a company_id explicitly",
        )
    if user.company_id is None:
        raise HTTPException(status_code=403, detail="user is not assigned to a company")
    return user.company_id


def scope_company_query(stmt: Select, column, scope: TenantScope) -> Select:
    """Apply the tenant filter on a company-keyed query; no-op for platform users."""
    if scope.is_platform:
        return stmt
    return stmt.where(column == scope.company_id)


def scope_or_platform_query(stmt: Select, column, scope: TenantScope) -> Select:
    """Tenant filter for *shared* resources (platform rows have ``company_id IS NULL``).

    A tenant sees its own rows plus platform-wide rows; platform operators see
    everything. Use this for catalogs that the platform itself provisions
    (notification channels, notification rules).
    """
    if scope.is_platform:
        return stmt
    from sqlalchemy import or_

    return stmt.where(or_(column == scope.company_id, column.is_(None)))


async def company_id_for_site(session, site_id: uuid.UUID) -> uuid.UUID | None:
    from sqlalchemy import select

    from fmp.models import Site

    row = (
        await session.execute(select(Site.company_id).where(Site.id == site_id))
    ).first()
    return row[0] if row else None


async def company_id_for_station(session, station_id: uuid.UUID) -> uuid.UUID | None:
    from sqlalchemy import select

    row = (
        await session.execute(
            select(Site.company_id)
            .join(Station, Station.site_id == Site.id)
            .where(Station.id == station_id)
        )
    ).first()
    return row[0] if row else None


async def company_id_for_tank(session, tank_id: uuid.UUID) -> uuid.UUID | None:
    from sqlalchemy import select

    row = (
        await session.execute(
            select(Site.company_id)
            .join(Tank, Tank.site_id == Site.id)
            .where(Tank.id == tank_id)
        )
    ).first()
    return row[0] if row else None
