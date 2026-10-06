"""Dispensing API endpoints: Excel upload, code validation, settlement.

Endpoints
---------
* POST /api/v1/dispensing/upload                    – ingest Excel/CSV quota sheet
* POST /api/v1/dispensing/validate                  – authorize a code at a station
* POST /api/v1/dispensing/complete                  – settle a dispense transaction
* POST /api/v1/dispensing/upload/{id}/dispatch      – (re)dispatch batch codes
* GET  /api/v1/dispensing/allocations               – list quota allocations
* GET  /api/v1/dispensing/transactions              – list dispense transactions
"""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from fmp.api.deps import CurrentUser, PrivilegedUser, SessionDep
from fmp.core.database import get_session
from fmp.core.device_auth import require_station
from fmp.core.redis import RedisClient, get_redis_client
from fmp.core.tenancy import scope_company_query, tenant_scope
from fmp.models import Allocation, Company, DispenseTransaction, Site, Station, UploadBatch
from fmp.schemas.dispensing import (
    CodeValidateRequest,
    CodeValidateResponse,
    DispenseCompleteRequest,
    DispenseCompleteResponse,
)
from fmp.schemas.dispensing_read import AllocationRead, TransactionRead
from fmp.schemas.notifications import ExcelIngestOutcome
from fmp.services.dispensing.dispense_engine import complete_dispense, validate_code
from fmp.services.dispensing.excel_ingestion import ingest_excel
from fmp.services.notifications.dispatcher import dispatch_codes

router = APIRouter(prefix="/api/v1/dispensing", tags=["dispensing"])


@router.post("/upload", response_model=ExcelIngestOutcome, status_code=201)
async def upload_quota_sheet(
    current: PrivilegedUser,
    file: UploadFile = File(...),
    company_id: uuid.UUID = Form(...),
    session: AsyncSession = Depends(get_session),
    redis: RedisClient = Depends(get_redis_client),
) -> ExcelIngestOutcome:
    """Parse the quota Excel file and generate single-use codes for each row.

    Operator-authenticated (was unauthenticated): an anonymous caller could mint
    fuel-authorization codes for any company. ``uploaded_by_id`` is taken from the
    authenticated caller, not from the form, and the target company must be the
    caller's own tenant.
    """
    if not file.filename:
        raise HTTPException(400, "missing filename")

    scope = tenant_scope(current)
    if not scope.is_platform and company_id != scope.company_id:
        raise HTTPException(403, "cannot upload a quota sheet for another company")
    company = await session.get(Company, company_id)
    if company is None or company.deleted_at is not None:
        raise HTTPException(404, "company not found")
    uploaded_by_id = current.id

    tmp = Path("/tmp") / f"quota_{uuid.uuid4().hex}_{Path(file.filename).name}"
    try:
        content = await file.read()
        tmp.write_bytes(content)
        outcome = await ingest_excel(
            session,
            redis,
            path=tmp,
            original_filename=file.filename,
            company_id=company_id,
            uploaded_by_id=uploaded_by_id,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    finally:
        tmp.unlink(missing_ok=True)

    # Fire-and-forget notification dispatch for the newly generated codes.
    if outcome.pending_dispatch:
        await dispatch_codes(outcome.pending_dispatch)

    return outcome


@router.post("/validate", response_model=CodeValidateResponse)
async def validate(
    req: CodeValidateRequest,
    station: Station = Depends(require_station),
    session: AsyncSession = Depends(get_session),
    redis: RedisClient = Depends(get_redis_client),
) -> CodeValidateResponse:
    """Authorize a single-use code **at the station**.

    Device-authenticated (G-002): the controller presents ``X-Station-Key`` and
    may only authorize codes for its own station — the body cannot claim another
    station.
    """
    _require_own_station(station, req.station_id)
    return await validate_code(session, redis, req)


@router.post("/complete", response_model=DispenseCompleteResponse)
async def complete(
    req: DispenseCompleteRequest,
    station: Station = Depends(require_station),
    session: AsyncSession = Depends(get_session),
    redis: RedisClient = Depends(get_redis_client),
) -> DispenseCompleteResponse:
    """Settle a dispense transaction. Device-authenticated (G-002)."""
    _require_own_station(station, req.station_id)
    return await complete_dispense(session, redis, req)


def _require_own_station(authenticated: Station, claimed: uuid.UUID) -> None:
    """Reject a device that authenticates as one station but claims another."""
    if authenticated.id != claimed:
        raise HTTPException(403, "device is not authorized for this station")


@router.post("/upload/{batch_id}/dispatch")
async def redispatch_batch_codes(
    batch_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _user: PrivilegedUser = None,
) -> dict:
    """Placeholder hook for re-dispatching an already-uploaded batch.

    Plaintext codes are not persisted, so re-dispatch requires operator
    re-entry of the original file (security by design). The endpoint returns
    guidance and validates the batch exists.
    """
    batch = await session.get(UploadBatch, batch_id)
    if batch is None:
        raise HTTPException(404, "batch not found")
    scope = tenant_scope(_user)
    if not scope.is_platform:
        uploader_company = await _company_of_user(session, batch.uploaded_by_id)
        if uploader_company is None or uploader_company != scope.company_id:
            raise HTTPException(404, "batch not found")
    return {
        "message": (
            "Plaintext codes are intentionally not persisted. "
            "Re-upload the original sheet to regenerate; a re-send is audited in notification_logs."
        ),
        "batch_id": str(batch.id),
        "status": batch.status,
    }


async def _company_of_user(session: AsyncSession, user_id: uuid.UUID) -> uuid.UUID | None:
    from fmp.models import User

    row = (await session.execute(select(User.company_id).where(User.id == user_id))).first()
    return row[0] if row else None


@router.get("/allocations", response_model=list[AllocationRead])
async def list_allocations(
    user: CurrentUser,
    session: SessionDep,
    max_rows: int = Query(default=100, ge=1, le=500),
) -> list[AllocationRead]:
    """Read-only list of quota allocations (newest first) for dashboards."""
    stmt = select(Allocation).order_by(desc(Allocation.created_at)).limit(max_rows)
    stmt = scope_company_query(stmt, Allocation.company_id, tenant_scope(user))  # type: ignore[arg-type]
    rows = (await session.execute(stmt)).scalars().all()
    return [
        AllocationRead(
            id=a.id, employee_id=a.employee_id,
            employee_name=a.employee.name if a.employee else "",
            invoice_number=a.invoice_number,
            allocated_liters=a.allocated_liters,
            dispensed_liters=a.dispensed_liters,
            remaining_liters=a.remaining_liters,
            status=a.status, created_at=a.created_at,
        )
        for a in rows
    ]


@router.get("/transactions", response_model=list[TransactionRead])
async def list_transactions(
    user: CurrentUser,
    session: SessionDep,
    dispenser_id: uuid.UUID | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[TransactionRead]:
    """Read-only list of dispense transactions (newest first) for dashboards.

    Scoped to the caller's tenant through ``station -> site -> company``.
    """
    stmt = (
        select(DispenseTransaction)
        .join(Station, Station.id == DispenseTransaction.station_id)
        .join(Site, Site.id == Station.site_id)
        .order_by(desc(DispenseTransaction.created_at))
        .limit(limit)
    )
    stmt = scope_company_query(stmt, Site.company_id, tenant_scope(user))  # type: ignore[arg-type]
    if dispenser_id:
        stmt = stmt.where(DispenseTransaction.dispenser_id == dispenser_id)
    rows = (await session.execute(stmt)).scalars().all()
    return [
        TransactionRead(
            id=t.id, station_id=t.station_id, dispenser_id=t.dispenser_id,
            employee_id=t.employee_id,
            requested_liters=t.requested_liters, actual_liters=t.actual_liters,
            secret_totalizer_before=t.secret_totalizer_before,
            secret_totalizer_after=t.secret_totalizer_after,
            status=t.status, created_at=t.created_at,
        )
        for t in rows
    ]