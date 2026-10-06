"""Structured logging and request correlation (audit G-201).

Operators cannot debug a distributed system from free-text log lines that carry
no link between the HTTP request that caused a problem and the background job it
triggered. This module installs:

* a JSON log formatter, so log records are machine-parseable rather than
  greppable by eye,
* a request-id middleware that mints (or honours an inbound ``X-Request-ID``)
  per HTTP request, binds it to the log context and echoes it back as a
  response header, so a user-visible id can be turned into a log query,
* context helpers that let background tasks and workers attach the same
  correlation fields without threading them through every function signature.

The context is held in a :class:`contextvars.ContextVar`, which is correct for
async code: each request task sees its own value without leaking into siblings.
"""
from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar

#: Correlation fields carried on every record emitted inside a request or task.
#: The default is None rather than {} so no task can mutate a shared dict.
_log_context: ContextVar[dict | None] = ContextVar("fuel_log_context", default=None)

#: Header used to accept/propagate a caller-supplied correlation id.
REQUEST_ID_HEADER = "X-Request-ID"

#: Attributes LogRecord always carries that are not user fields.
_RESERVED = frozenset(
    ["args", "asctime", "created", "exc_info", "exc_text", "filename", "funcName", "levelname", "levelno", "lineno", "module", "msecs", "message", "msg", "name", "pathname", "process", "processName", "relativeCreated", "stack_info", "thread", "threadName", "taskName"]
)


def new_request_id() -> str:
    return uuid.uuid4().hex


def bind_context(**fields) -> None:
    """Attach correlation fields to the current context (replaces them)."""
    _log_context.set({k: v for k, v in fields.items() if v is not None})


def add_context(**fields) -> None:
    """Merge additional fields into the current context."""
    merged = dict(_log_context.get())
    merged.update({k: v for k, v in fields.items() if v is not None})
    _log_context.set(merged)


def clear_context() -> None:
    _log_context.set({})


def current_context() -> dict:
    return dict(_log_context.get() or {})


class JsonFormatter(logging.Formatter):
    """Render a record as one JSON object per line.

    Extra fields passed via ``logger.info(..., extra={...})`` are merged with the
    ambient correlation context. Anything not JSON-serialisable is stringified
    rather than raising inside the logging path — a logging failure must never
    take down the operation being logged.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(current_context())
        for key, value in record.__dict__.items():
            if key in _RESERVED or key.startswith("_"):
                continue
            payload.setdefault(key, value)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    """Install the JSON formatter on the root logger.

    Idempotent: safe to call from every entrypoint (API, ingestion, worker).
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level.upper())

    # Third-party loggers are noisy at INFO and add nothing here.
    for noisy in ("uvicorn.access", "sqlalchemy.engine.Engine", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    # uvicorn's own error log stays visible but shares the JSON shape.
    logging.getLogger("uvicorn.error").handlers = []
    logging.getLogger("uvicorn.error").propagate = True