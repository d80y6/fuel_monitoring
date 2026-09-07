"""Unit tests for the dispense engine's pure/response helpers."""
from __future__ import annotations

import uuid

from fmp.schemas.dispensing import DispenseCompleteRequest
from fmp.services.dispensing import dispense_engine as engine


def test_reject_codes_validators():
    assert engine._reject("x").valid is False


def test_valid_from_cache():
    cached = {
        "code_id": str(uuid.uuid4()),
        "employee_name": "Omar",
        "remaining_liters": 12.5,
    }
    resp = engine._valid_from_cache(cached)
    assert resp.valid and resp.remaining_liters == 12.5


def test_from_existing_maps_fields():
    txn = object.__new__(_T)
    txn.id = 99
    txn.actual_liters = 15.0
    txn.requested_liters = 15.0
    resp = engine._from_existing(txn)
    assert resp.success and resp.transaction_id == 99 and resp.actual_liters == 15.0


class _T:
    id: int
    actual_liters: float
    requested_liters: float


def test_complete_request_totalizer_sanity():
    good = DispenseCompleteRequest(
        code="123456", station_id=uuid.uuid4(), dispenser_id=uuid.uuid4(),
        requested_liters=10, actual_liters=10,
        secret_totalizer_before=0, secret_totalizer_after=1000,
    )
    assert good.secret_totalizer_after == 1000

    import pytest
    with pytest.raises(ValueError):
        DispenseCompleteRequest(
            code="123456", station_id=uuid.uuid4(), dispenser_id=uuid.uuid4(),
            requested_liters=10, actual_liters=10,
            secret_totalizer_before=5000, secret_totalizer_after=1000,
        )