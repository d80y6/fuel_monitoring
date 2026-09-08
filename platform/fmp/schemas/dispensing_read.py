"""Read-only DTOs for the dispensing/totalizer dashboards."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class AllocationRead(BaseModel):
    id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str
    invoice_number: str | None = None
    allocated_liters: float
    dispensed_liters: float
    remaining_liters: float
    status: str
    created_at: datetime


class TransactionRead(BaseModel):
    id: int
    station_id: uuid.UUID
    dispenser_id: uuid.UUID
    employee_id: uuid.UUID
    requested_liters: float
    actual_liters: float
    secret_totalizer_before: int
    secret_totalizer_after: int
    status: str
    created_at: datetime
