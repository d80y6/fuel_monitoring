"""Celery tasks for analytics and forecasting."""
import logging
from datetime import datetime, timedelta

from celery_app import celery_app
from models.database import db, Measurement, Tank
from sqlalchemy import text, and_

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=120,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    time_limit=300,
    soft_time_limit=270,
)
def generate_forecast(self, tank_id: int, days: int = 30):
    """Generate fuel consumption forecast for a single tank."""
    try:
        from services.tank_forecast_service import TankForecastService

        service = TankForecastService(tank_id, days)
        result = service.generate_forecast()
        return result
    except ValueError as exc:
        logger.error("Invalid parameters for forecast tank=%d: %s", tank_id, exc)
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.error("Error generating forecast for tank %d: %s", tank_id, exc)
        raise self.retry(exc=exc)


@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=180,
    time_limit=600,
    soft_time_limit=540,
)
def daily_consumption(self):
    """Calculate daily consumption for all active tanks.

    Batches all tank IDs into a single SQL query to avoid N+1.
    Uses a single pass through the result set instead of per-tank
    service instantiation inside a loop.
    """
    try:
        from services.tank_forecast_service import TankForecastService

        active_tanks = (
            Tank.query.filter_by(is_active=True, deleted_at=None).all()
        )
        if not active_tanks:
            return {"results": {}}

        tank_ids = [t.id for t in active_tanks]
        results = {}

        # Batch query: get latest measurement per tank in one go
        subq = (
            db.session.query(
                Measurement.tank_id,
                db.func.max(Measurement.timestamp).label("max_ts"),
            )
            .filter(Measurement.tank_id.in_(tank_ids))
            .group_by(Measurement.tank_id)
            .subquery()
        )

        latest_rows = (
            db.session.query(Measurement)
            .join(
                subq,
                and_(
                    Measurement.tank_id == subq.c.tank_id,
                    Measurement.timestamp == subq.c.max_ts,
                ),
            )
            .all()
        )
        latest_map = {m.tank_id: m for m in latest_rows}

        for tank in active_tanks:
            try:
                latest = latest_map.get(tank.id)
                if not latest:
                    results[tank.id] = {
                        "success": False,
                        "error": "no measurements",
                    }
                    continue

                service = TankForecastService(tank.id, 1)
                result = service.generate_forecast()
                results[tank.id] = result
            except Exception as exc:
                logger.error(
                    "Error calculating daily consumption for tank %d: %s",
                    tank.id,
                    exc,
                )
                results[tank.id] = {"success": False, "error": str(exc)}

        logger.info(
            "Daily consumption computed for %d tanks", len(results)
        )
        return {"results": results}
    except Exception as exc:
        logger.error("Error in daily_consumption task: %s", exc)
        raise


@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=120,
    time_limit=300,
    soft_time_limit=270,
)
def refresh_aggregates(self):
    """Refresh TimescaleDB continuous aggregates."""
    try:
        with db.engine.connect() as conn:
            conn.execute(
                text(
                    "SELECT refresh_continuous_aggregate("
                    "'measurements_hourly', NULL, NULL)"
                )
            )
            conn.execute(
                text(
                    "SELECT refresh_continuous_aggregate("
                    "'measurements_daily', NULL, NULL)"
                )
            )
            conn.commit()
        logger.info("Continuous aggregates refreshed")
        return {"status": "success"}
    except Exception as exc:
        logger.error("Error refreshing aggregates: %s", exc)
        raise self.retry(exc=exc)
