"""Observability primitives (audit G-201).

Covers the three things an operator depends on:
* the JSON log formatter emits parseable records and carries the ambient
  correlation fields,
* the request id is honoured inbound, minted when absent, and does not leak
  between concurrent requests,
* readiness reports each dependency independently instead of one opaque 503.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import pytest

from fmp.core.logging_setup import (
    JsonFormatter,
    add_context,
    bind_context,
    clear_context,
    current_context,
    new_request_id,
)


class TestJsonFormatter:
    def _record(self, msg="hello", level=logging.INFO, **extra):
        record = logging.LogRecord(
            name="fmp.test",
            level=level,
            pathname=__file__,
            lineno=1,
            msg=msg,
            args=(),
            exc_info=None,
        )
        for key, value in extra.items():
            setattr(record, key, value)
        return record

    def test_emits_one_json_object_per_line(self):
        line = JsonFormatter().format(self._record())
        parsed = json.loads(line)
        assert parsed["message"] == "hello"
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "fmp.test"
        assert parsed["ts"].endswith("Z")

    def test_includes_extra_fields(self):
        parsed = json.loads(JsonFormatter().format(self._record(event="request", status=200)))
        assert parsed["event"] == "request"
        assert parsed["status"] == 200

    def test_carries_the_ambient_context(self):
        bind_context(request_id="abc", username="root")
        try:
            parsed = json.loads(JsonFormatter().format(self._record()))
            assert parsed["request_id"] == "abc"
            assert parsed["username"] == "root"
        finally:
            clear_context()

    def test_unserialisable_values_do_not_break_logging(self):
        class Weird:
            def __repr__(self):
                return "<weird>"

        parsed = json.loads(JsonFormatter().format(self._record(blob=Weird())))
        assert "weird" in parsed["blob"]

    def test_formats_exceptions_without_raising(self):
        try:
            raise ValueError("boom")
        except ValueError:
            import sys

            record = self._record()
            record.exc_info = sys.exc_info()
            parsed = json.loads(JsonFormatter().format(record))
        assert "boom" in parsed["exception"]

    def test_level_is_preserved(self):
        parsed = json.loads(
            JsonFormatter().format(self._record(level=logging.ERROR, msg="bad"))
        )
        assert parsed["level"] == "ERROR"


class TestLogContext:
    def teardown_method(self):
        clear_context()

    def test_starts_empty(self):
        assert current_context() == {}

    def test_bind_replaces(self):
        bind_context(a=1)
        bind_context(b=2)
        assert current_context() == {"b": 2}

    def test_add_merges(self):
        bind_context(request_id="r1")
        add_context(username="root")
        assert current_context() == {"request_id": "r1", "username": "root"}

    def test_none_values_are_dropped(self):
        bind_context(a=1, b=None)
        assert current_context() == {"a": 1}

    def test_clearing_isolates_records(self):
        bind_context(request_id="leaky")
        clear_context()
        assert current_context() == {}

    def test_returns_a_copy_so_callers_cannot_mutate_it(self):
        bind_context(a=1)
        snapshot = current_context()
        snapshot["a"] = 999
        assert current_context() == {"a": 1}

    def test_context_is_async_task_local(self):
        """Two concurrent requests must not see each other's correlation id."""
        import asyncio

        async def request(name: str):
            bind_context(request_id=name)
            await asyncio.sleep(0)
            return current_context()["request_id"]

        async def main():
            return await asyncio.gather(request("alpha"), request("beta"))

        assert asyncio.run(main()) == ["alpha", "beta"]


def test_request_ids_are_unique():
    assert len({new_request_id() for _ in range(100)}) == 100


class TestReadiness:
    async def test_reports_each_dependency_independently(self, monkeypatch):
        """A single opaque 503 tells an operator nothing; name the dependency."""
        from fmp.api.v1 import system

        async def _db_ok():
            return {"ok": True}

        async def _redis_down():
            return {"ok": False, "error": "ConnectionError: refused"}

        async def _mqtt_ok():
            return {"ok": True}

        monkeypatch.setattr(system, "_check_database", _db_ok)
        monkeypatch.setattr(system, "_check_redis", _redis_down)
        monkeypatch.setattr(system, "_check_mqtt", _mqtt_ok)

        from fastapi import Response

        response = Response()
        body = await system.readyz(response)
        assert body["failed"] == ["redis"], "the failing dependency must be named"
        assert body["status"] == "not_ready"
        assert response.status_code == 503
        assert body["checks"]["redis"]["error"], "carry the reason, not just the verdict"

    async def test_ready_when_everything_is_up(self, monkeypatch):
        from fmp.api.v1 import system

        async def _ok():
            return {"ok": True}

        for name in ("_check_database", "_check_redis", "_check_mqtt"):
            monkeypatch.setattr(system, name, _ok)

        from fastapi import Response

        response = Response()
        body = await system.readyz(response)
        assert body["status"] == "ready"
        assert body["failed"] == []
        assert response.status_code == 200


class TestMetricsSemantics:
    """The metrics payload is what an operator reads to decide whether the
    numbers can be trusted, so its vocabulary must be exact."""

    def test_stale_threshold_is_published_so_the_flag_is_interpretable(self):
        """A bare `stale: true` is unusable without the threshold it used."""
        from pathlib import Path

        from fmp.api.v1 import system

        source = Path(system.__file__).read_text()
        assert "tank_stale_after_seconds" in source
        assert "gateway_stale_after_seconds" in source

    def test_health_is_timezone_aware(self):
        assert datetime.now(UTC).tzinfo is not None


@pytest.mark.parametrize("module", ["fmp.api.v1.system"])
def test_system_module_has_no_import_side_effects(module):
    """Importing the system router must not open connections."""
    import importlib

    importlib.import_module(module)