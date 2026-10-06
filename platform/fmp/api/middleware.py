"""Request correlation and access logging (audit G-201).

Adds an ``X-Request-ID`` to every request and every response, binds it to the
logging context so all lines emitted while handling that request carry it, and
emits one structured access-log record per request with the outcome.

Honouring an inbound ``X-Request-ID`` matters operationally: the reverse proxy and
any upstream caller already speak this convention, so a trace started at the
edge survives into the application logs instead of being replaced.
"""
from __future__ import annotations

import logging
import time
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from fmp.core.logging_setup import (
    REQUEST_ID_HEADER,
    add_context,
    bind_context,
    clear_context,
    new_request_id,
)

logger = logging.getLogger("fmp.access")

#: Paths whose access logging is noise rather than signal.
_QUIET_PATHS = frozenset({"/api/v1/health", "/api/v1/readyz", "/api/v1/healthz", "/metrics"})

#: Request ids longer than this are truncated: an inbound header is
#: attacker-controlled and must not be able to bloat the log store.
_MAX_REQUEST_ID = 64


class CorrelationMiddleware(BaseHTTPMiddleware):
    """Bind a request id to the logging context for the life of the request."""

    async def dispatch(self, request: Request, call_next):
        inbound = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = inbound[:_MAX_REQUEST_ID] if inbound else new_request_id()
        request.state.request_id = request_id

        bind_context(request_id=request_id)
        add_context(
            method=request.method,
            path=request.url.path,
            client=request.client.host if request.client else None,
        )

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "unhandled error",
                extra={"event": "request_failed", "duration_ms": round(
                    (time.perf_counter() - started) * 1000, 2
                )},
            )
            clear_context()
            raise

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers[REQUEST_ID_HEADER] = request_id

        if request.url.path not in _QUIET_PATHS:
            # Read the actor from request.state, not the log context: Starlette's
            # BaseHTTPMiddleware runs the downstream app in a separate task, so a
            # ContextVar written by the auth dependency never reaches this frame.
            # state is per-request and does propagate.
            logger.info(
                "request",
                extra={
                    "event": "request",
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                    "username": getattr(request.state, "username", None),
                    "role": getattr(request.state, "role", None),
                },
            )
        clear_context()
        return response


def request_id_from(request: Request) -> str:
    """The id bound to this request (mints one if the middleware has not run)."""
    return getattr(request.state, "request_id", None) or uuid4().hex


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Baseline response headers.

    nginx sets the framing/CSP headers in production; these cover the case where
    the app is served directly (local dev, tests, a single-container deploy) so
    the protections are not silently absent.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response