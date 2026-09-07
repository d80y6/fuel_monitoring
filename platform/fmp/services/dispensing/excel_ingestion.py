"""Excel/CSV ingestion service + bulk single-use code generation.

Excel contract (per the dispensing spec):
    1. Employee ID (str)
    2. Name          (str)
    3. Phone         (str, up to 15 digits, MSISDN format)
    4. Invoice Number (str, optional)
    5. Allocated Liters (float > 0)

For each valid row an :class:`Allocation` is created and a fresh single-use
authorization code is generated and hashed. The plaintext codes are returned
once (for immediate notification dispatch) and never persisted.

Validation is row-level; a bad row is skipped and recorded in the batch error
log without failing the whole upload. Empty sheets / wrong header sets are
rejected wholesale.
"""
from __future__ import annotations

import asyncio
import csv
import json
import logging
import random
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from fmp.core.config import get_settings
from fmp.core.redis import RedisClient
from fmp.models import Allocation, DispenseCode, Employee, UploadBatch
from fmp.schemas.dispensing import ExcelIngestResult, ExcelRowOutput
from fmp.schemas.notifications import ExcelIngestOutcome, PendingDispatch
from fmp.services.dispensing.code_generator import code_expiry, generate_unique_code

logger = logging.getLogger(__name__)
settings = get_settings()

# Excel column-name → canonical field mapping (case-insensitive, trimmed).
COLUMN_ALIASES = {
    "employee id": "employee_id",
    "employee_id": "employee_id",
    "الرقم الوظيفي": "employee_id",
    "name": "name",
    "employee name": "name",
    "employee_name": "name",
    "name (english)": "name",
    "الاسم": "name",
    "phone": "phone",
    "phone number": "phone",
    "mobile": "phone",
    "mobile number": "phone",
    "رقم الهاتف": "phone",
    "invoice number": "invoice_number",
    "invoice_no": "invoice_number",
    "invoice": "invoice_number",
    "رقم الفاتورة": "invoice_number",
    "allocated liters": "allocated_liters",
    "allocated_liters": "allocated_liters",
    "liters": "allocated_liters",
    "allocation (l)": "allocated_liters",
    "Litres": "allocated_liters",
    "اللترات": "allocated_liters",
}

VALID_FIELDS = {"employee_id", "name", "phone", "invoice_number", "allocated_liters"}
PHONE_RE = re.compile(r"^\+?[1-9]\d{6,14}$")
EMPLOYEE_ID_RE = re.compile(r"^[A-Za-z0-9_\-\.]{1,64}$")


@dataclass
class _Row:
    row_index: int
    result: ExcelRowOutput
    code: str | None = None
    code_hash: str | None = None
    code_fp: str | None = None
    is_error: bool = False

    @classmethod
    def error(cls, row_index: int, employee_id: str, msg: str) -> "_Row":
        return cls(
            row_index=row_index,
            result=ExcelRowOutput(
                row=row_index, employee_id=employee_id or "-", employee_name="",
                phone="", error=msg,
            ),
            is_error=True,
        )

    @classmethod
    def ok(cls, fields: dict, row_index: int) -> "_Row":
        return cls(
            row_index=row_index,
            result=ExcelRowOutput(
                row=row_index,
                employee_id=fields["employee_id"],
                employee_name=fields["name"],
                phone=fields["phone"],
                invoice_number=fields.get("invoice_number"),
                allocated_liters=fields["allocated_liters"],
            ),
        )


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------
def _read_xlsx(path: Path) -> list[tuple[int, list[str]]]:
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows: list[tuple[int, list[str]]] = []
    for i, row in enumerate(ws.iter_rows(values_only=True), start=1):
        if row is None:
            continue
        cells = ["" if c is None else str(c).strip() for c in row]
        if any(cells):
            rows.append((i, cells))
    wb.close()
    return rows


def _read_csv(path: Path) -> list[tuple[int, list[str]]]:
    rows: list[tuple[int, list[str]]] = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        for i, row in enumerate(csv.reader(f), start=1):
            cells = [c.strip() for c in row]
            if any(cells):
                rows.append((i, cells))
    return rows


def _normalise_headers(header_cells: list[str]) -> dict[str, int]:
    """Map canonical field → column index from header row (aliases, any order)."""
    mapping: dict[str, int] = {}
    for idx, cell in enumerate(header_cells):
        key = COLUMN_ALIASES.get(cell.strip().lower()) or COLUMN_ALIASES.get(cell.strip())
        if key in VALID_FIELDS and key not in mapping:
            mapping[key] = idx
    return mapping


def _coerce_liters(value: str) -> float | None:
    try:
        liters = float(str(value).replace(",", "").strip())
    except (ValueError, TypeError):
        return None
    if not (0 < liters <= 10_000):
        return None
    return round(liters, 3)


# --------------------------------------------------------------------------
# Ingestion
# --------------------------------------------------------------------------
async def ingest_excel(
    session: AsyncSession,
    redis: RedisClient,
    *,
    path: Path,
    original_filename: str | None = None,
    company_id: uuid.UUID,
    uploaded_by_id: uuid.UUID,
) -> ExcelIngestOutcome:
    """Parse, validate, create allocations/codes for a company's quota sheet."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".xlsx" or suffix == ".xls":
        rows = _read_xlsx(path)
    elif suffix == ".csv":
        rows = _read_csv(path)
    else:
        raise ValueError(f"Unsupported file type: {suffix}")

    if not rows:
        raise ValueError("Workbook is empty")

    headers = _normalise_headers(rows[0][1])
    missing = VALID_FIELDS - set(headers)
    if missing:
        raise ValueError(
            f"Required columns missing: {', '.join(sorted(missing))}. "
            "Expected: Employee ID, Name, Phone, Invoice Number, Allocated Liters."
        )

    batch = UploadBatch(
        filename=path.name,
        original_filename=original_filename or path.name,
        uploaded_by_id=uploaded_by_id,
        total_rows=len(rows) - 1,
        status="PROCESSING",
    )
    session.add(batch)
    await session.flush()

    # Fast pre-existing fingerprint check: load once from DB into memory.
    parsed_rows: list[_Row] = []
    for row_index, cells in rows[1:]:
        row = _parse_row(row_index, cells, headers)
        parsed_rows.append(row)

    existing_fps = await _load_existing_fingerprints(session)
    existing_hashes: set[str] = set()
    for row in parsed_rows:
        if row.is_error:
            continue
        try:
            code, code_hash, code_fp = await generate_unique_code(
                redis,
                existing_hashes_check=lambda h, _e=existing_hashes: _membership_async(h, _e),
                existing_fingerprints_check=lambda f, _e=existing_fps: _membership_async(f, _e),
            )
            row.code, row.code_hash, row.code_fp = code, code_hash, code_fp
            existing_fps.add(code_fp)
            existing_hashes.add(code_hash)
        except Exception as exc:  # noqa: BLE001 — row-level isolation
            logger.warning("Row %d code generation failed: %s", row.row_index, exc)
            parsed_rows[parsed_rows.index(row)] = _Row.error(
                row.row_index, row.result.employee_id, str(exc)
            )

    # Persist allocations + codes (single round-trip per row via flush is fine
    # at typical batch sizes; switch to executemany for thousands of rows).
    created: list[_Row] = []
    pending: list[PendingDispatch] = []
    for row in parsed_rows:
        if row.is_error or row.code is None:
            continue
        employee = await _get_or_create_employee(session, row.result, company_id)
        alloc = Allocation(
            employee_id=employee.id,
            upload_batch_id=batch.id,
            company_id=company_id,
            invoice_number=row.result.invoice_number,
            allocated_liters=row.result.allocated_liters,
            dispensed_liters=0.0,
            remaining_liters=row.result.allocated_liters,
            status="PENDING",
        )
        session.add(alloc)
        await session.flush()
        session.add(
            DispenseCode(
                allocation_id=alloc.id,
                code_hash=row.code_hash,
                code_fp=row.code_fp,
                code_length=len(row.code),
                authorized_liters=row.result.allocated_liters,
                consumed_liters=0.0,
                status="ACTIVE",
                max_attempts=settings.CODE_MAX_ATTEMPTS,
                expires_at=code_expiry(),
            )
        )
        created.append(row)
        pending.append(
            PendingDispatch(
                allocation_id=alloc.id,
                employee_id=row.result.employee_id,
                employee_name=row.result.employee_name,
                phone=row.result.phone,
                code=row.code,
                liters=row.result.allocated_liters,
                invoice_number=row.result.invoice_number,
            )
        )

    batch.successful_rows = len(created)
    batch.failed_rows = len(parsed_rows) - len(created)
    batch.error_log = _errors_json(parsed_rows)
    batch.status = "COMPLETED"
    await session.commit()

    errors_out = [r.result for r in parsed_rows if r.is_error]
    return ExcelIngestOutcome(
        result=ExcelIngestResult(
            batch_id=batch.id,
            total_rows=batch.total_rows,
            successful_rows=batch.successful_rows,
            failed_rows=batch.failed_rows,
            errors=errors_out,
        ),
        pending_dispatch=pending,
    )


def _parse_row(row_index: int, cells: list[str], headers: dict[str, int]) -> _Row:
    def get(field: str) -> str:
        idx = headers.get(field)
        return cells[idx] if idx is not None and idx < len(cells) else ""

    employee_id = get("employee_id").strip()
    name = get("name").strip()
    phone = get("phone").strip()
    invoice = get("invoice_number").strip()
    liters = _coerce_liters(get("allocated_liters"))

    if not employee_id:
        return _Row.error(row_index, "", "missing employee_id")
    if not EMPLOYEE_ID_RE.match(employee_id):
        return _Row.error(row_index, employee_id, "invalid employee_id format")
    if not name:
        return _Row.error(row_index, employee_id, "missing name")
    if not PHONE_RE.match(phone):
        return _Row.error(row_index, employee_id, "invalid/missing phone (expect E.164)")
    if liters is None:
        return _Row.error(row_index, employee_id, "invalid allocated_liters")

    return _Row.ok(
        {
            "employee_id": employee_id,
            "name": name,
            "phone": phone,
            "invoice_number": invoice or None,
            "allocated_liters": liters,
        },
        row_index,
    )


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
async def _membership_async(key: str, bucket: set[str]) -> bool:
    return key in bucket


async def _load_existing_fingerprints(session: AsyncSession) -> set[str]:
    from sqlalchemy import select

    res = await session.execute(select(DispenseCode.code_fp))
    return {row[0] for row in res.all()}


async def _get_or_create_employee(
    session: AsyncSession, result: ExcelRowOutput, company_id: uuid.UUID
) -> Employee:
    from sqlalchemy import select

    emp = (
        await session.execute(
            select(Employee).where(
                Employee.company_id == company_id,
                Employee.employee_id == result.employee_id,
            )
        )
    ).scalar_one_or_none()
    if emp is not None:
        return emp
    emp = Employee(
        employee_id=result.employee_id,
        name=result.employee_name,
        phone=result.phone,
        company_id=company_id,
        is_active=True,
    )
    session.add(emp)
    await session.flush()
    return emp


def _errors_json(rows: list[_Row]) -> str:
    payload = [
        {"row": r.row_index, "employee_id": r.result.employee_id, "error": r.result.error}
        for r in rows
        if r.is_error
    ]
    return json.dumps(payload, ensure_ascii=False) if payload else "[]"


def _plaintext_codes(rows: list[_Row]) -> list[str]:
    return [r.code for r in rows if not r.is_error and r.code]