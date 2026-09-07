"""Celery application for the platform (Redis broker)."""
from __future__ import annotations

from celery import Celery
from fmp.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "fuel_platform",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "fmp.workers.tasks.dispensing",
        "fmp.workers.tasks.notifications",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
    result_expires=3600,
)