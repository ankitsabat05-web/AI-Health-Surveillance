from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.health_report import HealthReport

# Adapt these imports to your actual security modules.
from app.security.authentication import get_current_user
from app.security.authorization import require_health_official

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin",
    tags=["Administration"],
    dependencies=[Depends(require_health_official)],
)

DbSession = Annotated[Session, Depends(get_db)]


# ============================================================
# RESPONSE SCHEMAS
# ============================================================

class DailyReportSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_date: date
    total_reports: int = Field(ge=0)
    pending_reports: int = Field(ge=0)
    reviewed_reports: int = Field(ge=0)
    rejected_reports: int = Field(ge=0)


class DiseaseCount(BaseModel):
    disease_name: str
    report_count: int = Field(ge=0)


class RegionalCount(BaseModel):
    region_id: str
    report_count: int = Field(ge=0)


class AdminDashboardSummary(BaseModel):
    report_date: date
    total_reports_today: int = Field(ge=0)
    pending_reports: int = Field(ge=0)
    reviewed_reports: int = Field(ge=0)
    rejected_reports: int = Field(ge=0)
    top_reported_diseases: list[DiseaseCount]
    regions_with_most_reports: list[RegionalCount]


class DailyTrendPoint(BaseModel):
    report_date: date
    report_count: int = Field(ge=0)


class DiseaseTrendResponse(BaseModel):
    disease_name: str
    start_date: date
    end_date: date
    points: list[DailyTrendPoint]


# ============================================================
# DATE HELPERS
# ============================================================

def utc_day_bounds(day: date) -> tuple[datetime, datetime]:
    """
    Return UTC start and end times for a day.

    This assumes created_at timestamps are stored in UTC.
    If your reporting uses Indian Standard Time, convert the
    local reporting-day boundaries to UTC before querying.
    """
    start = datetime.combine(
        day,
        time.min,
        tzinfo=timezone.utc,
    )
    end = start + timedelta(days=1)

    return start, end


# ============================================================
# DATABASE QUERY HELPERS
# ============================================================

def _daily_status_counts(
    db: Session,
    start: datetime,
    end: datetime,
) -> tuple[int, int, int, int]:
    """
    Calculate daily report totals with database aggregation.

    This assumes the HealthReport model has a status field
    containing pending, reviewed, or rejected.
    """

    total_query = select(func.count(HealthReport.id)).where(
        HealthReport.created_at >= start,
        HealthReport.created_at < end,
    )

    pending_query = select(func.count(HealthReport.id)).where(
        HealthReport.created_at >= start,
        HealthReport.created_at < end,
        HealthReport.status == "pending",
    )

    reviewed_query = select(func.count(HealthReport.id)).where(
        HealthReport.created_at >= start,
        HealthReport.created_at < end,
        HealthReport.status == "reviewed",
    )

    rejected_query = select(func.count(HealthReport.id)).where(
        HealthReport.created_at >= start,
        HealthReport.created_at < end,
        HealthReport.status == "rejected",
    )

    return (
        db.scalar(total_query) or 0,
        db.scalar(pending_query) or 0,
        db.scalar(reviewed_query) or 0,
        db.scalar(rejected_query) or 0,
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@router.get(
    "/dashboard",
    response_model=AdminDashboardSummary,
)
def get_admin_dashboard(
    db: DbSession,
    report_date: date | None = Query(
        default=None,
        description="Reporting date. Defaults to the current UTC date.",
    ),
) -> AdminDashboardSummary:
    """
    Return aggregated health-report statistics for the dashboard.

    Only authenticated users who pass require_health_official
    can access this endpoint.
    """

    selected_date = report_date or datetime.now(timezone.utc).date()
    start, end = utc_day_bounds(selected_date)

    try:
        total, pending, reviewed, rejected = _daily_status_counts(
            db,
            start,
            end,
        )

        disease_query = (
            select(
                HealthReport.disease_name,
                func.count(HealthReport.id).label("report_count"),
            )
            .where(
                HealthReport.created_at >= start,
                HealthReport.created_at < end,
                HealthReport.disease_name.is_not(None),
            )
            .group_by(HealthReport.disease_name)
            .order_by(func.count(HealthReport.id).desc())
            .limit(10)
        )

        disease_rows = db.execute(disease_query).all()

        region_query = (
            select(
                HealthReport.region_id,
                func.count(HealthReport.id).label("report_count"),
            )
            .where(
                HealthReport.created_at >= start,
                HealthReport.created_at < end,
                HealthReport.region_id.is_not(None),
            )
            .group_by(HealthReport.region_id)
            .order_by(func.count(HealthReport.id).desc())
            .limit(10)
        )

        region_rows = db.execute(region_query).all()

        return AdminDashboardSummary(
            report_date=selected_date,
            total_reports_today=total,
            pending_reports=pending,
            reviewed_reports=reviewed,
            rejected_reports=rejected,
            top_reported_diseases=[
                DiseaseCount(
                    disease_name=name,
                    report_count=count,
                )
                for name, count in disease_rows
                if name
            ],
            regions_with_most_reports=[
                RegionalCount(
                    region_id=str(region_id),
                    report_count=count,
                )
                for region_id, count in region_rows
                if region_id
            ],
        )

    except SQLAlchemyError as exc:
        logger.exception("Admin dashboard query failed.")
        raise HTTPException(
            status_code=503,
            detail="Dashboard data is temporarily unavailable.",
        ) from exc


# ============================================================
# DAILY REPORT STATISTICS
# ============================================================

@router.get(
    "/reports/daily",
    response_model=DailyReportSummary,
)
def get_daily_report_summary(
    db: DbSession,
    report_date: date | None = Query(
        default=None,
    ),
) -> DailyReportSummary:
    selected_date = report_date or datetime.now(timezone.utc).date()
    start, end = utc_day_bounds(selected_date)

    try:
        total, pending, reviewed, rejected = _daily_status_counts(
            db,
            start,
            end,
        )

        return DailyReportSummary(
            report_date=selected_date,
            total_reports=total,
            pending_reports=pending,
            reviewed_reports=reviewed,
            rejected_reports=rejected,
        )

    except SQLAlchemyError as exc:
        logger.exception("Daily report statistics query failed.")
        raise HTTPException(
            status_code=503,
            detail="Daily report statistics are temporarily unavailable.",
        ) from exc


# ============================================================
# DISEASE REPORT TRENDS
# ============================================================

@router.get(
    "/trends/disease",
    response_model=DiseaseTrendResponse,
)
def get_disease_trend(
    db: DbSession,
    disease_name: Annotated[
        str,
        Query(min_length=2, max_length=100),
    ],
    start_date: date,
    end_date: date,
) -> DiseaseTrendResponse:
    """
    Return daily report counts for one disease.

    Counts represent reports, not necessarily clinically confirmed cases.
    """

    if end_date < start_date:
        raise HTTPException(
            status_code=422,
            detail="end_date must be on or after start_date.",
        )

    if (end_date - start_date).days > 365:
        raise HTTPException(
            status_code=422,
            detail="The requested date range cannot exceed 366 days.",
        )

    disease_name = disease_name.strip()

    if not disease_name:
        raise HTTPException(
            status_code=422,
            detail="disease_name cannot be empty.",
        )

    start, _ = utc_day_bounds(start_date)
    end, _ = utc_day_bounds(end_date + timedelta(days=1))

    try:
        # Database-side aggregation avoids loading every report.
        day_expression = func.date(HealthReport.created_at)

        query = (
            select(
                day_expression.label("report_date"),
                func.count(HealthReport.id).label("report_count"),
            )
            .where(
                HealthReport.created_at >= start,
                HealthReport.created_at < end,
                func.lower(HealthReport.disease_name)
                == disease_name.lower(),
            )
            .group_by(day_expression)
            .order_by(day_expression.asc())
        )

        rows = db.execute(query).all()

        points = [
            DailyTrendPoint(
                report_date=(
                    raw_date
                    if isinstance(raw_date, date)
                    else date.fromisoformat(str(raw_date))
                ),
                report_count=count,
            )
            for raw_date, count in rows
        ]

        return DiseaseTrendResponse(
            disease_name=disease_name,
            start_date=start_date,
            end_date=end_date,
            points=points,
        )

    except (SQLAlchemyError, ValueError, TypeError) as exc:
        logger.exception("Disease trend query failed.")
        raise HTTPException(
            status_code=503,
            detail="Disease trend data is temporarily unavailable.",
        ) from exc