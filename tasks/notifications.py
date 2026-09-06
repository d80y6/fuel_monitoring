"""Celery tasks for notifications."""
import hashlib
import json
import logging
import os
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from celery_app import celery_app

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Redis-backed deduplication helper
# ---------------------------------------------------------------------------
_NOTIF_DEDUP_TTL = 3600  # 1 hour


def _dedup_key(alarm_id: int, tank_id: int) -> str:
    raw = f"notif:{tank_id}:{alarm_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _is_duplicate(alarm_id: int, tank_id: int) -> bool:
    """Return True if this alarm was already notified within the dedup window."""
    try:
        import redis as _redis

        r = _redis.Redis.from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            decode_responses=True,
            socket_connect_timeout=3,
        )
        key = f"notif_dedup:{_dedup_key(alarm_id, tank_id)}"
        if r.exists(key):
            return True
        r.setex(key, _NOTIF_DEDUP_TTL, "1")
        return False
    except Exception:
        # If Redis is unavailable, do not block notifications.
        return False


def _send_email(subject: str, body: str, to_addrs: list) -> bool:
    """Send an email via SMTP. Returns True on success."""
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")
    from_addr = os.environ.get("SMTP_FROM", smtp_user)

    if not smtp_host or not to_addrs:
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr or "fuel-monitor@localhost"
    msg["To"] = ", ".join(to_addrs)
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            if smtp_port == 587:
                server.starttls()
            if smtp_user and smtp_pass:
                server.login(smtp_user, smtp_pass)
            server.sendmail(from_addr, to_addrs, msg.as_string())
        logger.info("Email sent to %s: %s", to_addrs, subject)
        return True
    except smtplib.SMTPException as exc:
        logger.error("SMTP error: %s", exc)
        return False
    except Exception as exc:
        logger.error("Email send failed: %s", exc)
        return False


def _resolve_recipients(tank_id: int) -> list:
    """Look up notification email recipients for a tank."""
    try:
        from models.database import Tank, Site, User, user_sites, user_companies

        tank = Tank.query.get(tank_id)
        if not tank or not tank.site:
            return []

        site = tank.site
        company = site.company
        emails = set()

        # Site contact
        if site.contact_email:
            emails.add(site.contact_email)
        # Company contact
        if company and company.contact_email:
            emails.add(company.contact_email)
        # Users with site access
        site_users = (
            User.query.join(user_sites, user_sites.c.user_id == User.id)
            .filter(user_sites.c.site_id == site.id, User.is_active == True)
            .all()
        )
        for u in site_users:
            if u.email:
                emails.add(u.email)
        # Users with company access
        if company:
            company_users = (
                User.query.join(
                    user_companies, user_companies.c.user_id == User.id
                )
                .filter(
                    user_companies.c.company_id == company.id,
                    User.is_active == True,
                )
                .all()
            )
            for u in company_users:
                if u.email:
                    emails.add(u.email)

        return list(emails)
    except Exception as exc:
        logger.error("Error resolving recipients for tank %d: %s", tank_id, exc)
        return []


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------
@celery_app.task(
    bind=True,
    max_retries=5,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    time_limit=90,
    soft_time_limit=60,
)
def send_notification(self, alarm_id: int, tank_id: int):
    """Send alarm notification via email with fallback to logging.

    Includes deduplication to avoid sending repeated notifications for the
    same alarm within a configurable window.
    """
    try:
        if _is_duplicate(alarm_id, tank_id):
            logger.info(
                "Skipping duplicate notification for alarm %d / tank %d",
                alarm_id,
                tank_id,
            )
            return {"status": "skipped", "reason": "duplicate"}

        from models.database import Alarm, Tank

        alarm = Alarm.query.get(alarm_id)
        if not alarm:
            logger.warning("Alarm %d not found", alarm_id)
            return {"status": "error", "reason": "alarm_not_found"}

        tank = Tank.query.get(tank_id)
        tank_name = tank.name if tank else f"Tank #{tank_id}"
        site_name = (
            tank.site.name
            if tank and tank.site
            else "Unknown Site"
        )

        subject = f"[{alarm.level.upper()}] Fuel Alert: {tank_name} - {alarm.type}"
        body = (
            f"Fuel Tank Alert\n"
            f"================\n"
            f"Tank:     {tank_name}\n"
            f"Site:     {site_name}\n"
            f"Type:     {alarm.type}\n"
            f"Level:    {alarm.level}\n"
            f"Message:  {alarm.message}\n"
            f"Value:    {alarm.value}\n"
            f"Time:     {alarm.timestamp}\n"
            f"Alarm ID: {alarm.id}\n"
        )

        recipients = _resolve_recipients(tank_id)
        sent = False
        if recipients:
            sent = _send_email(subject, body, recipients)

        if sent:
            logger.info(
                "Notification sent for alarm %d -> %s", alarm_id, recipients
            )
            return {"status": "sent", "alarm_id": alarm_id, "recipients": recipients}
        else:
            logger.warning(
                "Email not sent (no recipients or SMTP failed). "
                "Alarm %d logged: %s",
                alarm_id,
                alarm.message,
            )
            return {"status": "logged", "alarm_id": alarm_id}
    except Exception as exc:
        logger.error("Error sending notification for alarm %d: %s", alarm_id, exc)
        raise self.retry(exc=exc)
