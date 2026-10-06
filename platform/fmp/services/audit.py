"""Audit-event writer — single helper used by routers and services.

Fail-open: an audit write failure must never break the business operation,
but it is logged loudly at ERROR level.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from fmp.models import AuditEvent

logger = logging.getLogger(__name__)


def record(
    session: AsyncSession,
    *,
    actor,
    action: str,
    entity_type: str,
    entity_id=None,
    company_id: uuid.UUID | None | object = ...,  # sentinel: default = actor's company
    detail: dict | None = None,
) -> None:
    """Enqueue an audit row on the session (committed with the business txn)."""
    try:
        cid = actor.company_id if company_id is ... else company_id
        session.add(
            AuditEvent(
                actor_id=getattr(actor, "id", None),
                actor_username=getattr(actor, "username", None),
                company_id=cid,
                action=action,
                entity_type=entity_type,
                entity_id=str(entity_id) if entity_id is not None else None,
                detail=detail,
            )
        )
    except Exception:  # pragma: no cover — defensive
        logger.exception("audit recording failed for action=%s", action)
