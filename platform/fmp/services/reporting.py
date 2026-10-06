"""Reporting service (audit G-108).

Server-side reports over the real persisted data, tenant-scoped. Each report is
available as JSON (for the UI) and CSV (for operators who need to open it in a
spreadsheet), from the same code path, so the two can never disagree.

Every calculation is documented on the function that performs it, and every
report states the assumptions it makes. Nothing here invents numbers: a report
over an empty window returns an empty body with the window echoed back, not
zeroes that read like a real measurement.

Assumptions that apply throughout
---------------------------------
* All windows are half-open ``[start, end]`` in UTC.
* Consumption is the sum of positive hour-over-hour volume *drops* (see
  :func:`fmp.services.analytics.consumption.daily_consumption_series`): a rise
  is a delivery, not negative consumption.
* Inventory variance compares the last measured volume in the window against the
  last measured volume before it. It is a reconciliation signal, not a
  dispensing totalizer — the platform does not see fuel leaving the tank except
  through these measurements.
"""
from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import text

#: A report window longer than this is rejected rather than silently truncated.
MAX_WINDOW_DAYS = 366

_LEVELS = ("WARNING", "CRITICAL")


@dataclass(frozen=True)
class ReportWindow:
    start: datetime
    end: datetime

    @property
    def days(self) -> float:
        return (self.end - self.start).total_seconds() / 86400.0


def normalise_window(start: datetime, end: datetime) -> ReportWindow:
    """Validate and normalise a requested window to UTC, half-open."""
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    else:
        start = start.astimezone(UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    else:
        end = end.astimezone(UTC)
    if end <= start:
        raise ValueError("end must be after start")
    if end - start > timedelta(days=MAX_WINDOW_DAYS):
        raise ValueError(f"window must not exceed {MAX_WINDOW_DAYS} days")
    return ReportWindow(start=start, end=end)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _scoped_tanks(session, scope, *, tank_ids: list[uuid.UUID] | None, site_id: uuid.UUID | None):
    """Tank ids the caller may report on, honouring optional filters."""

    stmt = text(
        "SELECT t.id, t.name, t.tank_shape, t.tank_height, t.tank_volume, "
        "       t.site_id, s.name AS site_name, co.name AS company_name "
        "FROM tanks t "
        "JOIN sites s ON s.id = t.site_id "
        "JOIN companies co ON co.id = s.company_id "
        "WHERE t.deleted_at IS NULL"
    )
    params: dict = {}
    where: list[str] = []
    if not scope.is_platform:
        where.append("s.company_id = :company_id")
        params["company_id"] = str(scope.company_id)
    if site_id is not None:
        where.append("t.site_id = :site_id")
        params["site_id"] = str(site_id)
    if tank_ids:
        where.append("t.id = ANY(:tank_ids)")
        params["tank_ids"] = [str(t) for t in tank_ids]
    if where:
        stmt = text(stmt.text + " AND " + " AND ".join(where))
    rows = (await session.execute(stmt, params)).all()
    return rows


# ---------------------------------------------------------------------------
# Report 1 — tank inventory
# ---------------------------------------------------------------------------
async def tank_inventory_report(session, scope, window: ReportWindow, *, site_id=None) -> dict:
    """Current contents of every tank in scope, with freshness.

    Columns are deliberately explicit about provenance: ``volume_liters`` is a
    *measurement*, ``age_seconds`` is how stale it is, and ``stale`` is true once
    the reading is older than the platform's staleness threshold — so a tank
    reporting "full" from a probe that died last week is visibly not fresh rather
    than being presented as current stock.
    """
    from fmp.core.config import get_settings

    settings = get_settings()
    tanks = await _scoped_tanks(session, scope, tank_ids=None, site_id=site_id)

    rows: list[dict] = []
    for tank in tanks:
        latest = (
            await session.execute(
                text(
                    "SELECT timestamp, volume, gov_volume, net_volume, level, "
                    "       fill_percent, temperature, density_at_temperature, status "
                    "FROM measurements WHERE tank_id = :tid "
                    "ORDER BY timestamp DESC LIMIT 1"
                ),
                {"tid": tank.id},
            )
        ).first()
        first_in_window = (
            await session.execute(
                text(
                    "SELECT timestamp, volume FROM measurements "
                    "WHERE tank_id = :tid AND timestamp >= :s AND timestamp < :e "
                    "ORDER BY timestamp ASC LIMIT 1"
                ),
                {"tid": tank.id, "s": window.start, "e": window.end},
            )
        ).first()

        if latest is None:
            rows.append({
                "tank_id": str(tank.id),
                "tank_name": tank.name,
                "site": tank.site_name,
                "organization": tank.company_name,
                "capacity_liters": tank.tank_volume,
                "volume_liters": None,
                "fill_percent": None,
                "level_meters": None,
                "temperature_c": None,
                "measured_at": None,
                "age_seconds": None,
                "stale": True,
                "change_in_window_liters": None,
                "status_flag": None,
                "data_quality": "no telemetry recorded",
            })
            continue

        age = (datetime.now(UTC) - latest.timestamp).total_seconds()
        delta = None
        if first_in_window is not None:
            delta = round((latest.volume or 0.0) - (first_in_window.volume or 0.0), 3)

        rows.append({
            "tank_id": str(tank.id),
            "tank_name": tank.name,
            "site": tank.site_name,
            "organization": tank.company_name,
            "capacity_liters": tank.tank_volume,
            "volume_liters": latest.volume,
            "gov_volume_liters": latest.gov_volume,
            "net_volume_liters": latest.net_volume,
            "fill_percent": latest.fill_percent,
            "level_meters": latest.level,
            "temperature_c": latest.temperature,
            "density_kg_m3": latest.density_at_temperature,
            "measured_at": latest.timestamp.isoformat(),
            "age_seconds": round(age, 1),
            "stale": age > settings.TANK_STALE_AFTER_SECONDS,
            "change_in_window_liters": delta,
            "status_flag": latest.status,
            "data_quality": "measured" if age <= settings.TANK_STALE_AFTER_SECONDS else "stale",
        })

    return {
        "report": "tank_inventory",
        "generated_at": datetime.now(UTC).isoformat(),
        "window": {"start": window.start.isoformat(), "end": window.end.isoformat()},
        "columns": [
            "tank_name", "site", "organization", "capacity_liters", "volume_liters",
            "fill_percent", "level_meters", "temperature_c", "measured_at",
            "age_seconds", "stale", "change_in_window_liters", "data_quality",
        ],
        "assumptions": [
            "volume_liters is the last recorded measurement, not an estimate.",
            f"stale is true once a reading is older than {settings.TANK_STALE_AFTER_SECONDS}s.",
            "change_in_window_liters compares the last reading in the window with the first.",
        ],
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# Report 2 — consumption
# ---------------------------------------------------------------------------
async def consumption_report(session, scope, window: ReportWindow, *, site_id=None) -> dict:
    """Fuel drawn per tank per UTC day.

    Consumption is derived from volume *drops* between consecutive hourly
    samples. A rise is treated as a delivery and contributes nothing, so a
    refuelling event does not offset real consumption — this is the same series
    the dashboard and the forecast use, so the report cannot disagree with them.
    """
    from fmp.services.analytics.consumption import (
        daily_consumption_series,
        hourly_last_volumes,
    )

    tanks = await _scoped_tanks(session, scope, tank_ids=None, site_id=site_id)
    rows: list[dict] = []
    totals: dict[date, float] = {}

    # The series buckets by hour and takes last(volume) per bucket, so a bucket
    # boundary sits at or before the window start. Feeding a non-hour-aligned
    # start made the first bucket fall outside the window and be dropped, which
    # silently under-counted the first delta of the report. Floor the start to
    # the hour so the opening bucket is always included; the existing per-day
    # filter still bounds the result to the requested window.
    series_start = window.start.replace(minute=0, second=0, microsecond=0)

    for tank in tanks:
        points = await hourly_last_volumes(session, tank.id, series_start, window.end)
        series = daily_consumption_series(points, series_start, window.end)
        for entry in series:
            day_iso = entry["date"]
            totals[day_iso] = totals.get(day_iso, 0.0) + entry["liters"]
            rows.append({
                "day": day_iso,
                "tank_id": str(tank.id),
                "tank_name": tank.name,
                "site": tank.site_name,
                "organization": tank.company_name,
                "consumed_liters": entry["liters"],
            })

    rows.sort(key=lambda r: (r["day"], r["tank_name"]))
    return {
        "report": "consumption",
        "generated_at": datetime.now(UTC).isoformat(),
        "window": {"start": window.start.isoformat(), "end": window.end.isoformat()},
        "columns": ["day", "tank_name", "site", "organization", "consumed_liters"],
        "assumptions": [
            "Consumption is the sum of positive hour-over-hour volume drops.",
            "A volume rise is a delivery and contributes nothing to consumption.",
            "Days are UTC calendar days; the trailing partial day is included if it has data.",
            "The window start is floored to the hour so the opening bucket is counted; "
            "no extra liters are invented, only the boundary bucket is included.",
        ],
        "rows": rows,
        "totals_by_day": [
            {"day": d, "consumed_liters": round(v, 3)} for d, v in sorted(totals.items())
        ],
        "grand_total_liters": round(sum(totals.values()), 3),
    }


# ---------------------------------------------------------------------------
# Report 3 — inventory variance
# ---------------------------------------------------------------------------
async def inventory_variance_report(
    session, scope, window: ReportWindow, *, site_id=None, tolerance_liters: float = 0.0
) -> dict:
    """Book-vs-measured reconciliation signal per tank.

    The platform has no independent inventory ledger for tank contents, so this
    reports the *measured* change across the window alongside the delivery
    volume recorded against allocations in the same period. A mismatch between
    them is what an operator investigates: it can be a meter error, an
    unrecorded transfer, or evaporation.

    ``tolerance_liters`` is the threshold above which a row is flagged; it is a
    caller-supplied business tolerance, not a platform default, so no row is
    silently judged "fine".
    """

    tanks = await _scoped_tanks(session, scope, tank_ids=None, site_id=site_id)
    rows: list[dict] = []

    for tank in tanks:
        first = (
            await session.execute(
                text(
                    "SELECT timestamp, volume FROM measurements "
                    "WHERE tank_id = :tid AND timestamp >= :s AND timestamp < :e "
                    "ORDER BY timestamp ASC LIMIT 1"
                ),
                {"tid": tank.id, "s": window.start, "e": window.end},
            )
        ).first()
        last = (
            await session.execute(
                text(
                    "SELECT timestamp, volume FROM measurements "
                    "WHERE tank_id = :tid AND timestamp >= :s AND timestamp < :e "
                    "ORDER BY timestamp DESC LIMIT 1"
                ),
                {"tid": tank.id, "s": window.start, "e": window.end},
            )
        ).first()

        if first is None or last is None:
            rows.append({
                "tank_id": str(tank.id),
                "tank_name": tank.name,
                "site": tank.site_name,
                "opening_liters": first.volume if first else None,
                "closing_liters": last.volume if last else None,
                "measured_change_liters": None,
                "booked_outflow_liters": None,
                "variance_liters": None,
                "within_tolerance": None,
                "note": "insufficient telemetry in window",
            })
            continue

        # Dispensing recorded against stations on this tank's site.
        booked = (
            await session.execute(
                text(
                    "SELECT COALESCE(SUM(dt.actual_liters), 0) "
                    "FROM dispense_transactions dt "
                    "JOIN stations st ON st.id = dt.station_id "
                    "WHERE st.site_id = :sid AND dt.created_at >= :s AND dt.created_at < :e "
                    "  AND dt.status <> 'REJECTED'"
                ),
                {"sid": tank.site_id, "s": window.start, "e": window.end},
            )
        ).scalar_one()

        measured_change = last.volume - first.volume
        # Measured change is negative when fuel left; booked is a positive outflow.
        variance = round(measured_change + float(booked), 3)

        rows.append({
            "tank_id": str(tank.id),
            "tank_name": tank.name,
            "site": tank.site_name,
            "opening_liters": round(first.volume, 3),
            "closing_liters": round(last.volume, 3),
            "opening_at": first.timestamp.isoformat(),
            "closing_at": last.timestamp.isoformat(),
            "measured_change_liters": round(measured_change, 3),
            "booked_outflow_liters": round(float(booked), 3),
            "variance_liters": variance,
            "within_tolerance": abs(variance) <= tolerance_liters,
            "note": "",
        })

    flagged = [r for r in rows if r.get("within_tolerance") is False]
    return {
        "report": "inventory_variance",
        "generated_at": datetime.now(UTC).isoformat(),
        "window": {"start": window.start.isoformat(), "end": window.end.isoformat()},
        "tolerance_liters": tolerance_liters,
        "columns": [
            "tank_name", "site", "opening_liters", "closing_liters",
            "measured_change_liters", "booked_outflow_liters",
            "variance_liters", "within_tolerance",
        ],
        "assumptions": [
            "measured_change_liters is the difference between the first and last "
            "measurement inside the window; a negative value means fuel left the tank.",
            "booked_outflow_liters sums actual_liters of non-rejected dispense "
            "transactions at this tank's site in the window.",
            "variance_liters = measured_change + booked_outflow; non-zero means the "
            "two views disagree and needs investigation.",
            "Booked outflow is attributed by SITE, not by tank: the platform records "
            "dispenses against stations, and tanks at one site are not individually "
            "metered against those transactions.",
        ],
        "rows": rows,
        "flagged_count": len(flagged),
    }


# ---------------------------------------------------------------------------
# Report 4 — alarm history
# ---------------------------------------------------------------------------
async def alarm_report(
    session, scope, window: ReportWindow, *, site_id=None, level: str | None = None
) -> dict:
    """Every alarm raised in the window, with its resolution state."""

    tanks = await _scoped_tanks(session, scope, tank_ids=None, site_id=site_id)
    rows: list[dict] = []
    counts = {"WARNING": 0, "CRITICAL": 0}
    resolved = unresolved = 0

    for tank in tanks:
        stmt = (
            text(
                "SELECT id, timestamp, type, level, message, value, state, "
                "       acknowledged_at, resolved_at, resolved_message "
                "FROM alarms WHERE tank_id = :tid AND timestamp >= :s AND timestamp < :e "
                "ORDER BY timestamp DESC"
            )
        )
        for row in (await session.execute(stmt, {"tid": tank.id, "s": window.start, "e": window.end})).all():
            if level and row.level != level:
                continue
            counts[row.level] = counts.get(row.level, 0) + 1
            if row.state == "resolved":
                resolved += 1
            else:
                unresolved += 1
            rows.append({
                "raised_at": row.timestamp.isoformat(),
                "tank_id": str(tank.id),
                "tank_name": tank.name,
                "site": tank.site_name,
                "organization": tank.company_name,
                "type": row.type,
                "level": row.level,
                "state": row.state,
                "message": row.message,
                "value": row.value,
                "acknowledged_at": row.acknowledged_at.isoformat() if row.acknowledged_at else None,
                "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
                "resolution": row.resolved_message,
            })

    rows.sort(key=lambda r: r["raised_at"], reverse=True)
    return {
        "report": "alarm_history",
        "generated_at": datetime.now(UTC).isoformat(),
        "window": {"start": window.start.isoformat(), "end": window.end.isoformat()},
        "columns": [
            "raised_at", "tank_name", "site", "organization", "type", "level",
            "state", "message", "resolved_at",
        ],
        "assumptions": [
            "An alarm is attributed to the tank that raised it.",
            "state is one of active / acknowledged / escalated / resolved / suppressed.",
            "A window shows alarms by the time they were RAISED, not resolved.",
        ],
        "rows": rows,
        "summary": {
            "total": len(rows),
            "by_level": counts,
            "resolved": resolved,
            "unresolved": unresolved,
        },
    }


# ---------------------------------------------------------------------------
# Report 5 — dispensing audit
# ---------------------------------------------------------------------------
async def dispensing_audit_report(session, scope, window: ReportWindow, *, site_id=None) -> dict:
    """Every dispense transaction in the window with its authorization trail."""

    params: dict = {"s": window.start, "e": window.end}
    where = ["dt.created_at >= :s", "dt.created_at < :e"]
    if not scope.is_platform:
        where.append("si.company_id = :company_id")
        params["company_id"] = str(scope.company_id)
    if site_id is not None:
        where.append("st.site_id = :site_id")
        params["site_id"] = str(site_id)

    rows = (
        await session.execute(
            text(
                "SELECT dt.id, dt.created_at, dt.requested_liters, dt.actual_liters, "
                "       dt.status, dt.secret_totalizer_before, dt.secret_totalizer_after, "
                "       emp.name AS employee_name, st.name AS station_name, "
                "       s.name AS site_name, co.name AS company_name, "
                "       al.invoice_number "
                "FROM dispense_transactions dt "
                "LEFT JOIN stations st ON st.id = dt.station_id "
                "LEFT JOIN sites s ON s.id = st.site_id "
                "LEFT JOIN companies co ON co.id = s.company_id "
                "LEFT JOIN employees emp ON emp.id = dt.employee_id "
                "LEFT JOIN allocations al ON al.id = dt.allocation_id "
                "WHERE " + " AND ".join(where) + " ORDER BY dt.created_at DESC"
            ),
            params,
        )
    ).all()

    out: list[dict] = []
    total_dispensed = 0.0
    total_delta = 0.0
    for row in rows:
        delta = (
            (row.secret_totalizer_after - row.secret_totalizer_before)
            if row.secret_totalizer_before is not None and row.secret_totalizer_after is not None
            else None
        )
        if delta is not None and row.status == "COMPLETED":
            total_delta += delta
        if row.status == "COMPLETED":
            total_dispensed += row.actual_liters or 0.0
        out.append({
            "dispensed_at": row.created_at.isoformat(),
            "organization": row.company_name,
            "site": row.site_name,
            "station": row.station_name,
            "employee": row.employee_name,
            "invoice": row.invoice_number,
            "requested_liters": row.requested_liters,
            "actual_liters": row.actual_liters,
            "status": row.status,
            "totalizer_before": row.secret_totalizer_before,
            "totalizer_after": row.secret_totalizer_after,
            "totalizer_delta": delta,
        })

    return {
        "report": "dispensing_audit",
        "generated_at": datetime.now(UTC).isoformat(),
        "window": {"start": window.start.isoformat(), "end": window.end.isoformat()},
        "columns": [
            "dispensed_at", "organization", "site", "station", "employee",
            "invoice", "requested_liters", "actual_liters", "status", "totalizer_delta",
        ],
        "assumptions": [
            "Only transactions with status COMPLETED contribute to the totals.",
            "totalizer_delta is the secret meter movement recorded with the transaction; "
            "it is the mechanical counter, independent of the authorization code.",
            "A non-null totalizer_delta that disagrees with actual_liters is a meter "
            "or tamper signal worth reviewing.",
        ],
        "rows": out,
        "summary": {
            "transactions": len(out),
            "completed": sum(1 for r in out if r["status"] == "COMPLETED"),
            "total_dispensed_liters": round(total_dispensed, 3),
            "total_totalizer_delta": total_delta,
        },
    }


# ---------------------------------------------------------------------------
# CSV rendering
# ---------------------------------------------------------------------------
def to_csv(report: dict) -> str:
    """Render a report's rows as CSV.

    Uses the report's own ``columns`` list so the CSV header can never drift
    from what the JSON payload documents.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(report["columns"])
    for row in report["rows"]:
        writer.writerow(["" if row.get(c) is None else row.get(c) for c in report["columns"]])
    return buffer.getvalue()