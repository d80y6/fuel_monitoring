"""Long-running tasks for Excel processing + notification dispatch."""
from __future__ import annotations

import uuid

from fmp.schemas.notifications import PendingDispatch
from fmp.services.notifications.dispatcher import dispatch_codes
from fmp.workers.celery_app import celery_app


@celery_app.task(name="notifications.dispatch_code")
def dispatch_code_task(
    allocation_id: str,
    employee_id: str,
    employee_name: str,
    phone: str,
    code: str,
    liters: float,
    invoice_number: str | None = None,
    channel: str | None = None,
) -> dict:
    """Dispatch one authorization code over SMS/WhatsApp."""
    import asyncio

    item = PendingDispatch(
        allocation_id=uuid.UUID(allocation_id),
        employee_id=employee_id,
        employee_name=employee_name,
        phone=phone,
        code=code,
        liters=liters,
        invoice_number=invoice_number,
    )
    result = asyncio.run(dispatch_codes([item]))[0]
    return result.model_dump()


@celery_app.task(name="notifications.dispatch_batch")
def dispatch_batch_task(payloads: list[dict]) -> list[dict]:
    """Dispatch many codes (batch) as a single task."""
    import asyncio

    items = [PendingDispatch(**p) for p in payloads]
    results = asyncio.run(dispatch_codes(items))
    return [r.model_dump() for r in results]