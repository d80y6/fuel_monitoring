"""Pydantic v2 schemas for the dispensing domain."""
from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field, model_validator


# ---- Excel ingestion -------------------------------------------------------
class ExcelRowOutput(BaseModel):
    row: int
    employee_id: str
    employee_name: str
    phone: str
    invoice_number: str | None = None
    allocated_liters: float | None = Field(default=None, gt=0, le=10_000)
    error: str | None = None


class ExcelIngestResult(BaseModel):
    batch_id: uuid.UUID
    total_rows: int
    successful_rows: int
    failed_rows: int
    errors: list[ExcelRowOutput]


# ---- Code generation -------------------------------------------------------
class AllocationCreated(BaseModel):
    allocation_id: uuid.UUID
    employee_id: str
    phone: str
    allocated_liters: float
    code: str  # plaintext, returned once for dispatch


# ---- Validation ------------------------------------------------------------
class CodeValidateRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8, pattern=r"^\d{6,8}$")
    station_id: uuid.UUID
    requested_liters: float | None = Field(default=None, gt=0, le=10_000)


class CodeValidateResponse(BaseModel):
    valid: bool
    employee_name: str | None = None
    remaining_liters: float | None = None
    code_id: uuid.UUID | None = None
    reason: str | None = None


# ---- Completion ------------------------------------------------------------
class DispenseCompleteRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8, pattern=r"^\d{6,8}$")
    station_id: uuid.UUID
    dispenser_id: uuid.UUID
    requested_liters: float = Field(gt=0, le=10_000)
    actual_liters: float = Field(gt=0, le=10_000)
    secret_totalizer_before: int = Field(ge=0)
    secret_totalizer_after: int = Field(ge=0)

    @model_validator(mode="after")
    def _check_totalizer_monotonic(self) -> "DispenseCompleteRequest":
        if self.secret_totalizer_after < self.secret_totalizer_before:
            raise ValueError("totalizer_after must be >= totalizer_before")
        return self


class PartialDispenseOutcome(BaseModel):
    partial: bool
    original_code_id: uuid.UUID
    dispensed_liters: float
    remaining_liters: float
    new_code: str | None = None
    new_code_id: uuid.UUID | None = None
    new_allocation_id: uuid.UUID | None = None


class DispenseCompleteResponse(BaseModel):
    success: bool
    transaction_id: int
    status: Literal["COMPLETED", "PARTIAL", "OVER_DISPENSE", "DISCREPANCY"]
    actual_liters: float
    requested_liters: float
    partial: PartialDispenseOutcome | None = None
    discrepancy_flag: str | None = None


class TotalizerAuditRequest(BaseModel):
    station_id: uuid.UUID
    dispenser_id: uuid.UUID
    totalizer_value: int = Field(ge=0)
    source: Literal["hardware", "backfill", "manual"] = "hardware"


class TotalizerAuditResult(BaseModel):
    ok: bool
    expected_cumulative: float | None = None
    observed_cumulative: float | None = None
    delta_liters: float | None = None
    flag: str | None = None