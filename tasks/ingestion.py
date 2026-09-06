"""Celery tasks for measurement ingestion."""
import logging
from datetime import datetime, timedelta

from celery_app import celery_app
from models.database import db, Measurement, Tank

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=5,
    default_retry_delay=30,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    time_limit=120,
    soft_time_limit=90,
)
def process_measurements(self, tank_id: int, measurement_data: dict):
    """Process a batch of measurements for a tank.

    This task is called by the MQTT ingestion service via ``.delay()``.
    """
    try:
        measurement = Measurement(
            tank_id=tank_id,
            timestamp=measurement_data.get("timestamp", datetime.utcnow()),
            pressure=measurement_data.get("pressure"),
            temperature=measurement_data.get("temperature"),
            level=measurement_data.get("level"),
            volume=measurement_data.get("volume"),
            flow_rate=measurement_data.get("flow_rate", 0.0),
            fill_percent=measurement_data.get("fill_percent"),
            status=measurement_data.get("status", 0),
        )
        db.session.add(measurement)
        db.session.commit()
        logger.info(
            "Processed measurement id=%d for tank=%d", measurement.id, tank_id
        )
        return {"status": "success", "measurement_id": measurement.id}
    except Exception as exc:
        db.session.rollback()
        logger.error("Error processing measurement for tank %d: %s", tank_id, exc)
        raise self.retry(exc=exc)


@celery_app.task(
    bind=True,
    max_retries=5,
    default_retry_delay=30,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    time_limit=60,
    soft_time_limit=45,
)
def check_alarms(self, tank_id: int, measurement_data: dict, thresholds: dict):
    """Check alarms for a measurement and dispatch notifications.

    Each triggered alarm is forwarded to ``send_notification`` via
    ``send_notification.delay()``.
    """
    try:
        from models.alarm_manager import AlarmManager
        from tasks.notifications import send_notification

        alarm_mgr = AlarmManager(tank_id, db.session)
        alarms = alarm_mgr.check_alarms(measurement_data, thresholds)

        dispatched = 0
        for alarm in alarms:
            send_notification.delay(alarm.id, tank_id)
            dispatched += 1

        logger.info(
            "Checked alarms for tank=%d, dispatched %d notifications",
            tank_id,
            dispatched,
        )
        return {"alarms": dispatched}
    except Exception as exc:
        logger.error("Error checking alarms for tank %d: %s", tank_id, exc)
        raise self.retry(exc=exc)


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    time_limit=300,
    soft_time_limit=270,
)
def cleanup_old_measurements(self):
    """Drop old measurement chunks using TimescaleDB ``drop_chunks()``.

    Falls back to a plain ``DELETE FROM`` for non-TimescaleDB deployments.
    """
    try:
        with db.engine.connect() as conn:
            try:
                result = conn.execute(
                    db.text(
                        "SELECT drop_chunks('measurement', "
                        "older_than => INTERVAL '90 days');"
                    )
                )
                conn.commit()
                logger.info("TimescaleDB drop_chunks completed")
                return {"status": "success", "method": "drop_chunks"}
            except Exception:
                logger.debug(
                    "drop_chunks unavailable, falling back to DELETE"
                )

            cutoff = datetime.utcnow() - timedelta(days=90)
            result = conn.execute(
                db.text(
                    "DELETE FROM measurement WHERE timestamp < :cutoff"
                ),
                {"cutoff": cutoff},
            )
            conn.commit()
            deleted = result.rowcount
            logger.info("Deleted %d old measurements via DELETE", deleted)
            return {"status": "success", "method": "delete", "deleted": deleted}
    except Exception as exc:
        logger.error("Error cleaning up old measurements: %s", exc)
        raise self.retry(exc=exc)
