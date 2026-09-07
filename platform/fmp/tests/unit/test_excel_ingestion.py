"""Unit tests for Excel/CSV row parsing and column mapping."""
from __future__ import annotations

from fmp.services.dispensing.excel_ingestion import (
    EMPLOYEE_ID_RE,
    PHONE_RE,
    _coerce_liters,
    _normalise_headers,
    _parse_row,
)

STANDARD_HEADERS = ["Employee ID", "Name", "Phone", "Invoice Number", "Allocated Liters"]


def _headers_dict():
    return _normalise_headers(STANDARD_HEADERS)


def test_header_normalisation():
    h = _headers_dict()
    assert h == {
        "employee_id": 0,
        "name": 1,
        "phone": 2,
        "invoice_number": 3,
        "allocated_liters": 4,
    }


def test_header_aliases_and_arabic():
    h = _normalise_headers(["الرقم الوظيفي", "الاسم", "رقم الهاتف", "اللترات"])
    assert sorted(h) == ["allocated_liters", "employee_id", "name", "phone"]


def test_missing_required_column_vanishes():
    h = _normalise_headers(["Employee ID", "Phone", "Allocated Liters"])
    assert "name" not in h


def test_valid_row():
    row = _parse_row(2, ["EMP-001", "Omar", "777111222", "INV-9", "50.5"], _headers_dict())
    assert not row.is_error
    assert row.result.employee_name == "Omar"
    assert row.result.allocated_liters == 50.5


def test_invalid_phone_rejected():
    row = _parse_row(2, ["EMP-001", "Omar", "notaphone", "INV-9", "10"], _headers_dict())
    assert row.is_error and "phone" in row.result.error


def test_zero_liters_rejected():
    row = _parse_row(2, ["EMP-001", "Omar", "777111222", "", "0"], _headers_dict())
    assert row.is_error


def test_coerce_liters_variants():
    assert _coerce_liters("1,200.5") == 1200.5
    assert _coerce_liters("50") == 50.0
    assert _coerce_liters("0") is None
    assert _coerce_liters("abc") is None
    assert _coerce_liters("50000") is None  # > 10_000 cap


def test_employee_id_regex():
    assert EMPLOYEE_ID_RE.match("EMP-1001_A")
    assert not EMPLOYEE_ID_RE.match("bad id!")
    assert PHONE_RE.match("+967773123456")
    assert not PHONE_RE.match("123")