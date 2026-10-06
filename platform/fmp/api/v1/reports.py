"""Reports API (audit G-108).

Five operator reports over real persisted data, tenant-scoped, each available as
JSON or CSV from the same code path. Report definitions and their assumptions
live in :mod:`fmp.services.reporting`; this module only handles the HTTP
concerns: authorization, parameters, and content type.

* ``GET /api/v1/reports/{report}``  — JSON body
* ``GET /api/v1/reports/{report}/export`` — ``text/csv`` download
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Response

from fmp.api.deps import CurrentUser, SessionDep
from fmp.core.tenancy import TenantScope, tenant_scope
from fmp.services.reporting import (
    alarm_report,
    consumption_report,
    dispensing_audit_report,
    inventory_variance_report,
    normalise_window,
    tank_inventory_report,
    to_csv,
)

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

#: report name -> (handler, required role). All are available to any
#: authenticated caller; the handler enforces the tenant scope.
_REPORTS = {
    "tank-inventory": tank_inventory_report,
    "consumption": consumption_report,
    "inventory-variance": inventory_variance_report,
    "alarms": alarm_report,
    "dispensing-audit": dispensing_audit_report,
}

#: Reports that accept these extra filters.
_VARIANCE_ONLY = {"tolerance_liters"}
_ALARM_ONLY = {"level"}


async def _build(
    name: str,
    current: CurrentUser,
    session: SessionDep,
    *,
    start: datetime,
    end: datetime,
    site_id: uuid.UUID | None,
    tolerance_liters: float,
    level: str | None,
) -> dict:
    handler = _REPORTS.get(name)
    if handler is None:
        raise HTTPException(404, f"unknown report '{name}'")
    try:
        window = normalise_window(start, end)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    if site_id is not None:
        await _require_site_in_scope(session, site_id, tenant_scope(current))

    scope: TenantScope = tenant_scope(current)
    if name == "inventory-variance":
        return await handler(session, scope, window, site_id=site_id, tolerance_liters=tolerance_liters)
    if name == "alarms":
        return await handler(session, scope, window, site_id=site_id, level=level)
    return await handler(session, scope, window, site_id=site_id)


async def _require_site_in_scope(session, site_id: uuid.UUID, scope: TenantScope) -> None:
    from fmp.models import Site

    site = (
        await session.execute(
            Site.__table__.select().where(
                Site.__table__.c.id == site_id, Site.__table__.c.deleted_at.is_(None)
            )
        )
    ).first()
    if site is None:
        raise HTTPException(404, "site not found")
    if not scope.is_platform and site.company_id != scope.company_id:
        raise HTTPException(404, "site not found")


@router.get("")
async def list_reports(current: CurrentUser) -> dict:
    """Catalogue of available reports, so the UI never hardcodes the list."""
    return {
        "reports": [
            {
                "name": name,
                "description": (handler.__doc__ or "").strip().split("\n")[0],
            }
            for name, handler in _REPORTS.items()
        ]
    }


@router.get("/{report}")
async def get_report(
    report: str,
    current: CurrentUser,
    session: SessionDep,
    start: datetime = Query(...),
    end: datetime = Query(...),
    site_id: uuid.UUID | None = Query(default=None),
    tolerance_liters: float = Query(default=0.0, ge=0),
    level: str | None = Query(default=None, pattern="^(WARNING|CRITICAL)$"),
) -> dict:
    """Run a report and return it as JSON."""
    return await _build(
        report, current, session, start=start, end=end, site_id=site_id,
        tolerance_liters=tolerance_liters, level=level,
    )


@router.get("/{report}/export")
async def export_report(
    report: str,
    current: CurrentUser,
    session: SessionDep,
    start: datetime = Query(...),
    end: datetime = Query(...),
    site_id: uuid.UUID | None = Query(default=None),
    tolerance_liters: float = Query(default=0.0, ge=0),
    level: str | None = Query(default=None, pattern="^(WARNING|CRITICAL)$"),
) -> Response:
    """Run the same report and stream it as CSV.

    Identical computation to the JSON route: the CSV is rendered from the JSON
    payload's own column list, so the two cannot disagree.
    """
    payload = await _build(
        report, current, session, start=start, end=end, site_id=site_id,
        tolerance_liters=tolerance_liters, level=level,
    )
    body = to_csv(payload)
    filename = f"{report}-{start.date().isoformat()}-{end.date().isoformat()}.csv"
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )