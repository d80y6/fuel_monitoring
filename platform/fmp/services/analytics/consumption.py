"""Daily consumption analytics + simple-moving-average forecast.

Consumption is derived from the tank's tracked volume: between consecutive
hourly ``last(volume)`` samples, a positive drop is fuel drawn (negative drops
are refills and contribute nothing). Drops are summed per UTC day. The forecast
is the simple mean of the most recent ``window_days`` daily values — the operator
chose SMA for this platform; no bespoke model is invented here.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text

HOURLY_BUCKET = "1 hour"


async def hourly_last_volumes(session, tank_id, start: datetime, end: datetime):
    """Per-hour ``last(volume, timestamp)`` over the range (hourly buckets)."""
    rows = await session.execute(
        text(
            f"SELECT time_bucket(interval '{HOURLY_BUCKET}', timestamp) AS ts, "
            "last(volume, timestamp) AS volume "
            "FROM measurements "
            "WHERE tank_id = :tid AND timestamp >= :start AND timestamp <= :end "
            "GROUP BY 1 ORDER BY 1"
        ),
        {"tid": tank_id, "start": start, "end": end},
    )
    return [(r.ts, r.volume) for r in rows]


def daily_consumption_series(points, start: datetime, end: datetime) -> list[dict]:
    """Sum positive hourly volume drops per UTC calendar day.

    A drop between samples at ``a`` then ``b`` occurs in the interval ``(a, b]``,
    i.e. during the day of the *earlier* sample, so each delta is attributed to
    ``a.date()``. Reads only count toward the day they end in.
    """
    daily: dict[date, float] = {}
    prev: tuple[datetime, float] | None = None
    for ts, volume in points:
        if ts < start or ts > end:
            continue
        if prev is None:
            prev = (ts, volume)
            continue
        prev_ts, prev_volume = prev
        if prev_ts >= start:
            delta = prev_volume - volume
            if delta > 0:
                day = prev_ts.date()
                daily[day] = daily.get(day, 0.0) + delta
        prev = (ts, volume)
    return [
        {"date": d.isoformat(), "liters": round(v, 3)}
        for d, v in sorted(daily.items())
    ]


def sma_forecast(series: list[dict], window_days: int) -> dict:
    """SMA over the most recent ``window_days`` daily liters; None when empty."""
    values = [p["liters"] for p in series[-max(window_days, 1):]]
    forecast = round(sum(values) / len(values), 3) if values else None
    return {"method": "sma", "window_days": window_days, "liters_per_day": forecast}


async def compute_consumption(
    session,
    tank_id,
    *,
    days: int,
    window_days: int,
) -> dict:
    """Full consumption payload (series + SMA forecast) for one tank.

    The window opens at UTC midnight ``days`` back so that every day in the
    series is a complete calendar day; the trailing (possibly partial) day is
    only present once it has readings of its own.
    """
    now = datetime.now(timezone.utc)
    end = now
    start = (now - timedelta(days=days)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    points = await hourly_last_volumes(session, tank_id, start, end)
    series = daily_consumption_series(points, start, end)
    return {
        "tank_id": str(tank_id),
        "days": days,
        "method": "sma",
        "forecast": sma_forecast(series, window_days),
        "series": series,
    }