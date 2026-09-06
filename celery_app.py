"""Celery application for Fuel Monitoring Platform."""
import os

from celery import Celery
from celery.schedules import crontab
from celery.utils.log import get_task_logger
from flask import Flask

logger = get_task_logger(__name__)

# Create Celery instance
celery_app = Celery(
    "fuel_monitoring",
    broker=os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
    include=[
        "tasks.ingestion",
        "tasks.analytics",
        "tasks.notifications",
        "tasks.export",
    ],
)

# ---------------------------------------------------------------------------
# Celery configuration
# ---------------------------------------------------------------------------
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # -- Routing --
    task_routes={
        "tasks.ingestion.process_measurements": {"queue": "ingestion"},
        "tasks.ingestion.check_alarms": {"queue": "notifications"},
        "tasks.ingestion.cleanup_old_measurements": {"queue": "ingestion"},
        "tasks.analytics.generate_forecast": {"queue": "analytics"},
        "tasks.analytics.daily_consumption": {"queue": "analytics"},
        "tasks.analytics.refresh_aggregates": {"queue": "analytics"},
        "tasks.notifications.send_notification": {"queue": "notifications"},
        "tasks.export.generate_csv": {"queue": "export"},
    },
    # -- Retry / backoff defaults (per-task overrides take precedence) --
    task_default_retry_delay=60,
    task_max_retries=3,
    # Exponential backoff: task decorators set retry_backoff=True etc.
    # This is the global fallback configuration.
    # -- Worker settings --
    worker_concurrency=int(os.environ.get("CELERY_WORKER_CONCURRENCY", "4")),
    worker_max_tasks_per_child=1000,
    # -- Task execution --
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Global default time limits (tasks can override via decorator)
    task_time_limit=600,
    task_soft_time_limit=540,
    # -- Result backend --
    result_expires=3600,
    result_backend_transport_options={"visibility_timeout": 3600},
    # -- Broker connection --
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=10,
    # -- Beat schedule --
    beat_schedule={
        "daily-consumption-report": {
            "task": "tasks.analytics.daily_consumption",
            "schedule": crontab(hour=0, minute=0),
        },
        "cleanup-expired-measurements": {
            "task": "tasks.ingestion.cleanup_old_measurements",
            "schedule": crontab(hour=2, minute=0),
        },
        "refresh-continuous-aggregates": {
            "task": "tasks.analytics.refresh_aggregates",
            "schedule": crontab(minute="*/30"),
        },
    },
)


# ---------------------------------------------------------------------------
# Flask integration — ensures every task runs inside an app context
# ---------------------------------------------------------------------------
def create_celery(app: Flask) -> Celery:
    """Create and configure the Celery instance with Flask app context.

    Every Celery task will automatically push ``app.app_context()``
    so that tasks can use Flask extensions (SQLAlchemy, etc.) without
    manual context management.
    """
    celery_app.conf.update(
        broker_url=app.config.get(
            "CELERY_BROKER_URL",
            os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0"),
        ),
        result_backend=app.config.get(
            "CELERY_RESULT_BACKEND",
            os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
        ),
    )

    TaskBase = celery_app.Task

    class ContextTask(TaskBase):
        abstract = True

        def __call__(self, *args, **kwargs):
            with app.app_context():
                return TaskBase.__call__(self, *args, **kwargs)

    celery_app.Task = ContextTask
    return celery_app
