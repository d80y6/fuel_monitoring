"""Event-driven notification dispatch (alarm rules).

This is the rule engine behind :class:`fmp.models.notifications.NotificationRule`:
an event (currently a raised alarm) is matched against the enabled rules for the
event type, ordered by severity, and every matching target receives the rendered
message through the rule's channel. Deliveries are written to
``notification_logs`` with the tenant stamped on each row, so the notification
history is tenant-scoped like everything else.

Used by the ingestion pipeline (fire-and-forget) and by the API's test-delivery
endpoint. No rule match means a silent no-op — never a fabricated "sent".
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fmp.models.notifications import NotificationGateway, NotificationRule
from fmp.schemas.notifications import EventDispatchSummary
from fmp.services.notifications.dispatcher import (
    CHANNEL_GATEWAY_TYPES,
    log_delivery,
    send_via_gateway,
)

logger = logging.getLogger(__name__)

#: Severity ordering for rule matching (WARNING rules also fire on CRITICAL).
LEVEL_RANK = {"WARNING": 1, "CRITICAL": 2}


def render_template(template: str | None, fallback: str, context: dict) -> str:
    """Render a rule template.

    ``str.format``-style ``{placeholders}`` are supported. A template that
    references an unknown key must never break delivery, so formatting errors
    fall back to the default message instead of raising.
    """
    if not template:
        return fallback
    try:
        return template.format(**context)
    except (KeyError, IndexError, ValueError) as exc:
        logger.warning("notification template render failed (%s); using default", exc)
        return fallback


async def load_matching_rules(
    session: AsyncSession,
    *,
    event_type: str,
    level: str,
    company_id: uuid.UUID | None,
    site_id: uuid.UUID | None,
    tank_id: uuid.UUID | None,
) -> list[NotificationRule]:
    """Enabled rules matching the event, tenant-scoped, platform rules included.

    A rule matches when its ``min_level`` is at or below the event level and it
    is scoped to the tenant (``company_id`` equal or NULL) and to the site
    (``site_id`` NULL = all sites of the tenant, or the exact site).
    """
    stmt = select(NotificationRule).where(
        NotificationRule.enabled.is_(True),
        NotificationRule.event_type == event_type,
    )
    if company_id is not None:
        from sqlalchemy import or_

        stmt = stmt.where(
            or_(NotificationRule.company_id == company_id, NotificationRule.company_id.is_(None))
        )
    rows = (await session.execute(stmt)).scalars().all()
    min_rank = LEVEL_RANK.get((level or "").upper(), 0)
    matched = []
    for rule in rows:
        if LEVEL_RANK.get((rule.min_level or "").upper(), 99) > min_rank:
            continue
        if rule.site_id is not None and site_id is not None and rule.site_id != site_id:
            continue
        matched.append(rule)
    return matched


async def _gateways_for_channel(
    session: AsyncSession, channel: str, company_id: uuid.UUID | None
) -> list[NotificationGateway]:
    stmt = (
        select(NotificationGateway)
        .where(NotificationGateway.is_active.is_(True))
        .order_by(NotificationGateway.priority.asc())
    )
    if company_id is not None:
        from sqlalchemy import or_

        stmt = stmt.where(
            or_(NotificationGateway.company_id == company_id, NotificationGateway.company_id.is_(None))
        )
    rows = (await session.execute(stmt)).scalars().all()
    allowed = CHANNEL_GATEWAY_TYPES.get(channel, {channel})
    return [g for g in rows if g.type in allowed]


async def dispatch_event(
    session: AsyncSession,
    *,
    event_type: str,
    level: str,
    company_id: uuid.UUID | None,
    site_id: uuid.UUID | None = None,
    tank_id: uuid.UUID | None = None,
    context: dict | None = None,
    default_message: str = "",
) -> EventDispatchSummary:
    """Send one event to every recipient matched by the enabled rules."""
    rules = await load_matching_rules(
        session,
        event_type=event_type,
        level=level,
        company_id=company_id,
        site_id=site_id,
        tank_id=tank_id,
    )
    summary = EventDispatchSummary(
        event_type=event_type, evaluated_rules=len(rules), sent=0, failed=0
    )
    if not rules:
        return summary

    ctx = dict(context or {})
    for rule in rules:
        gateways = await _gateways_for_channel(session, rule.channel, company_id)
        if not gateways:
            logger.warning(
                "notification rule %s matches channel %s but no active gateway is configured",
                rule.name,
                rule.channel,
            )
            summary.failed += len(rule.targets)
            continue
        gateway = gateways[0]
        for target in rule.targets:
            text = render_template(rule.template, default_message, ctx)
            try:
                provider_id = await send_via_gateway(gateway, target, text)
            except Exception as exc:  # noqa: BLE001 - never break the caller
                logger.warning("rule %s delivery to %s failed: %s", rule.name, target, exc)
                await log_delivery(
                    session,
                    gateway_id=gateway.id,
                    channel=rule.channel,
                    recipient=target,
                    status="FAILED",
                    error=f"{exc}",
                    retry=0,
                    event_type=event_type,
                    event_ref=ctx.get("event_ref"),
                    company_id=company_id,
                )
                summary.failed += 1
                continue
            await log_delivery(
                session,
                gateway_id=gateway.id,
                channel=rule.channel,
                recipient=target,
                status="SENT",
                provider_message_id=provider_id,
                retry=0,
                event_type=event_type,
                event_ref=ctx.get("event_ref"),
                company_id=company_id,
            )
            summary.sent += 1

    logger.info(
        "event %s dispatched: %s rule(s), %s sent, %s failed",
        event_type,
        summary.evaluated_rules,
        summary.sent,
        summary.failed,
    )
    return summary


async def send_test_message(
    session: AsyncSession,
    gateway: NotificationGateway,
    recipient: str,
    text: str,
    company_id: uuid.UUID | None,
) -> str:
    """Send one real message through a channel and log the outcome."""
    provider_id = await send_via_gateway(gateway, recipient, text)
    await log_delivery(
        session,
        gateway_id=gateway.id,
        channel=gateway.type,
        recipient=recipient,
        status="SENT",
        provider_message_id=provider_id,
        event_type="test",
        event_ref=None,
        company_id=company_id,
    )
    return provider_id


DEFAULT_TEST_TEXT = (
    "Fuel platform test notification. If you received this message the "
    "channel is configured correctly. Sent at {sent_at}."
)


def default_test_text() -> str:
    return DEFAULT_TEST_TEXT.format(sent_at=datetime.now(timezone.utc).isoformat())
