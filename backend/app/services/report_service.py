from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.health_report import HealthReport

logger = logging.getLogger("health_surveillance.report_service")

DEFAULT_TIMEZONE = "Asia/Kolkata"
MAX_REPORT_DAYS = 366


# ---------------------------------------
# Date and Validation Helpers
# ---------------------------------------

def _get_timezone(timezone_name: str = DEFAULT_TIMEZONE) -> ZoneInfo:
    """Validate and return the requested reporting timezone."""
    try:
        return ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid reporting timezone.",
        ) from None


def _validate_date_range(start_date: date, end_date: date) -> None:
    """Validate date range and limit expensive historical queries."""
    if start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Start date must not be after end date.",
        )

    if (end_date - start_date).days >= MAX_REPORT_DAYS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Date range cannot exceed {MAX_REPORT_DAYS} days.",
        )


def _local_date_bounds(
    start_date: date,
    end_date: date,
    timezone_name: str = DEFAULT_TIMEZONE,
) -> tuple[datetime, datetime]:
    """Return timezone-aware local boundaries."""
    tz = _get_timezone(timezone_name)

    start = datetime.combine(start_date, time.min, tzinfo=tz)
    end_exclusive = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=tz)

    return start, end_exclusive


def _base_filters(
    start: datetime,
    end_exclusive: datetime,
    region_id: str | None = None,
) -> list[Any]:
    filters: list[Any] = [
        HealthReport.created_at >= start,
        HealthReport.created_at < end_exclusive,
    ]

    if region_id is not None:
        normalized_region = region_id.strip()

        if not normalized_region:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Region ID cannot be empty.",
            )

        if len(normalized_region) > 100:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Region ID is too long.",
            )

        filters.append(HealthReport.region_id == normalized_region)

    return filters


def _database_error(operation: str) -> HTTPException:
    logger.error("Database operation failed: %s", operation)
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Report service is temporarily unavailable.",
    )


# ---------------------------------------
# Daily Summary
# ---------------------------------------

def get_daily_report(
    db: Session,
    *,
    report_date: date | None = None,
    region_id: str | None = None,
    timezone_name: str = DEFAULT_TIMEZONE,
) -> dict[str, Any]:
    """Generate a summary for one local calendar day."""
    tz = _get_timezone(timezone_name)
    selected_date = report_date or datetime.now(tz).date()

    start, end_exclusive = _local_date_bounds(
        selected_date,
        selected_date,
        timezone_name,
    )

    filters = _base_filters(start, end_exclusive, region_id)

    try:
        total_reports = db.scalar(
            select(func.count(HealthReport.id)).where(*filters)
        ) or 0

        status_rows = db.execute(
            select(
                HealthReport.status,
                func.count(HealthReport.id),
            )
            .where(*filters)
            .group_by(HealthReport.status)
        ).all()

        status_counts = {
            str(report_status): count
            for report_status, count in status_rows
        }

        disease_rows = db.execute(
            select(
                HealthReport.disease_name,
                func.count(HealthReport.id),
            )
            .where(
                *filters,
                HealthReport.disease_name.is_not(None),
            )
            .group_by(HealthReport.disease_name)
            .order_by(func.count(HealthReport.id).desc())
            .limit(10)
        ).all()

        return {
            "report_date": selected_date.isoformat(),
            "timezone": timezone_name,
            "region_id": region_id,
            "total_reports": total_reports,
            "status_counts": status_counts,
            "top_reported_diseases": [
                {
                    "disease_name": disease_name,
                    "report_count": count,
                }
                for disease_name, count in disease_rows
            ],
            "data_note": (
                "Counts represent submitted health reports. "
                "Disease names are not necessarily confirmed diagnoses."
            ),
        }

    except SQLAlchemyError:
        db.rollback()
        raise _database_error("get_daily_report") from None


# ---------------------------------------
# Historical Summary
# ---------------------------------------

def get_historical_report(
    db: Session,
    *,
    start_date: date,
    end_date: date,
    region_id: str | None = None,
    timezone_name: str = DEFAULT_TIMEZONE,
) -> dict[str, Any]:
    """Return daily report counts for a historical date range."""
    _validate_date_range(start_date, end_date)

    start, end_exclusive = _local_date_bounds(
        start_date,
        end_date,
        timezone_name,
    )

    filters = _base_filters(start, end_exclusive, region_id)

    try:
        rows = db.execute(
            select(
                func.date(HealthReport.created_at),
                func.count(HealthReport.id),
            )
            .where(*filters)
            .group_by(func.date(HealthReport.created_at))
            .order_by(func.date(HealthReport.created_at))
        ).all()

        counts_by_date = {
            str(day): count
            for day, count in rows
        }

        daily_counts = []
        current_date = start_date

        while current_date <= end_date:
            daily_counts.append(
                {
                    "date": current_date.isoformat(),
                    "report_count": counts_by_date.get(
                        current_date.isoformat(),
                        0,
                    ),
                }
            )
            current_date += timedelta(days=1)

        return {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "timezone": timezone_name,
            "region_id": region_id,
            "total_reports": sum(item["report_count"] for item in daily_counts),
            "daily_counts": daily_counts,
        }

    except SQLAlchemyError:
        db.rollback()
        raise _database_error("get_historical_report") from None


# ---------------------------------------
# Disease Report Statistics
# ---------------------------------------

def get_disease_report_statistics(
    db: Session,
    *,
    start_date: date,
    end_date: date,
    region_id: str | None = None,
    limit: int = 10,
    timezone_name: str = DEFAULT_TIMEZONE,
) -> dict[str, Any]:
    """Count reports grouped by reported disease name."""
    _validate_date_range(start_date, end_date)

    if not 1 <= limit <= 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Limit must be between 1 and 100.",
        )

    start, end_exclusive = _local_date_bounds(
        start_date,
        end_date,
        timezone_name,
    )

    filters = _base_filters(start, end_exclusive, region_id)
    filters.append(HealthReport.disease_name.is_not(None))

    try:
        rows = db.execute(
            select(
                HealthReport.disease_name,
                func.count(HealthReport.id).label("report_count"),
            )
            .where(*filters)
            .group_by(HealthReport.disease_name)
            .order_by(
                func.count(HealthReport.id).desc(),
                HealthReport.disease_name.asc(),
            )
            .limit(limit)
        ).all()

        return {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "region_id": region_id,
            "diseases": [
                {
                    "disease_name": disease_name,
                    "report_count": count,
                }
                for disease_name, count in rows
            ],
            "data_note": (
                "Based on disease names recorded in reports; "
                "not a substitute for clinically confirmed surveillance data."
            ),
        }

    except SQLAlchemyError:
        db.rollback()
        raise _database_error("get_disease_report_statistics") from None


# ---------------------------------------
# Regional Report Statistics
# ---------------------------------------

def get_regional_report_statistics(
    db: Session,
    *,
    start_date: date,
    end_date: date,
    limit: int = 20,
    timezone_name: str = DEFAULT_TIMEZONE,
) -> dict[str, Any]:
    """Rank regions by submitted report volume."""
    _validate_date_range(start_date, end_date)

    if not 1 <= limit <= 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Limit must be between 1 and 100.",
        )

    start, end_exclusive = _local_date_bounds(
        start_date,
        end_date,
        timezone_name,
    )

    filters = _base_filters(start, end_exclusive)

    try:
        rows = db.execute(
            select(
                HealthReport.region_id,
                func.count(HealthReport.id).label("report_count"),
            )
            .where(*filters)
            .group_by(HealthReport.region_id)
            .order_by(func.count(HealthReport.id).desc())
            .limit(limit)
        ).all()

        return {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "regions": [
                {
                    "region_id": region_id,
                    "report_count": count,
                }
                for region_id, count in rows
            ],
            "data_note": (
                "Higher report volume alone does not establish an outbreak. "
                "Population, reporting rates, and clinical validation "
                "should be considered."
            ),
        }

    except SQLAlchemyError:
        db.rollback()
        raise _database_error("get_regional_report_statistics") from None
