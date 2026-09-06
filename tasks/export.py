"""Celery tasks for data export."""
import csv
import logging
import os
import time as _time
from datetime import datetime, timedelta

from celery_app import celery_app
from models.database import db, Measurement, Tank

logger = logging.getLogger(__name__)

EXPORT_DIR = os.environ.get("EXPORT_DIR", "/tmp/fuel_exports")
os.makedirs(EXPORT_DIR, exist_ok=True)


@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    time_limit=600,
    soft_time_limit=540,
)
def generate_csv(
    self,
    tank_id: int,
    start_date: str = None,
    end_date: str = None,
    days: int = 7,
):
    """Generate a CSV export file for tank measurements.

    Supports explicit date range filtering via ``start_date`` /
    ``end_date`` (ISO format strings) or a relative ``days`` window.

    Streams rows to a file on disk and returns the file path and a
    download URL instead of embedding CSV content in Redis.
    """
    try:
        tank = Tank.query.get(tank_id)
        if not tank:
            return {"error": "Tank not found"}

        # Resolve date range
        end_dt = (
            datetime.fromisoformat(end_date)
            if end_date
            else datetime.utcnow()
        )
        start_dt = (
            datetime.fromisoformat(start_date)
            if start_date
            else end_dt - timedelta(days=days)
        )

        # Generate filename
        timestamp_str = _time.strftime("%Y%m%d_%H%M%S")
        filename = f"tank_{tank_id}_{timestamp_str}.csv"
        filepath = os.path.join(EXPORT_DIR, filename)

        # Build query with date range filter
        query = (
            Measurement.query.filter(
                Measurement.tank_id == tank_id,
                Measurement.timestamp >= start_dt,
                Measurement.timestamp <= end_dt,
            )
            .order_by(Measurement.timestamp.asc())
        )

        # Stream to file in chunks
        headers = [
            "Timestamp",
            "Pressure (bar)",
            "Temperature (°C)",
            "Level (m)",
            "Volume (L)",
            "Flow Rate (L/min)",
            "Fill (%)",
            "Status",
        ]

        row_count = 0
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)

            # Stream in batches to avoid loading everything into memory
            batch_size = 1000
            offset = 0
            while True:
                batch = query.offset(offset).limit(batch_size).all()
                if not batch:
                    break
                for m in batch:
                    writer.writerow(
                        [
                            m.timestamp.isoformat() if m.timestamp else "",
                            f"{m.pressure:.4f}" if m.pressure is not None else "",
                            f"{m.temperature:.2f}" if m.temperature is not None else "",
                            f"{m.level:.3f}" if m.level is not None else "",
                            f"{m.volume:.1f}" if m.volume is not None else "",
                            f"{m.flow_rate:.2f}" if m.flow_rate is not None else "",
                            f"{m.fill_percent:.1f}" if m.fill_percent is not None else "",
                            m.status if m.status is not None else "",
                        ]
                    )
                row_count += len(batch)
                offset += batch_size

        download_url = f"/api/exports/{filename}"
        logger.info(
            "CSV export generated: %s (%d rows, tank=%d, %s to %s)",
            filename,
            row_count,
            tank_id,
            start_dt.isoformat(),
            end_dt.isoformat(),
        )
        return {
            "status": "success",
            "file_path": filepath,
            "filename": filename,
            "download_url": download_url,
            "row_count": row_count,
            "start_date": start_dt.isoformat(),
            "end_date": end_dt.isoformat(),
        }
    except Exception as exc:
        logger.error("Error generating CSV for tank %d: %s", tank_id, exc)
        raise self.retry(exc=exc)
