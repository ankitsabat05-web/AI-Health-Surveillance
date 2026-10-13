# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportGeneralTypeIssues=false

import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.health_report import HealthReport
from app.security.authorization import require_health_official

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/dashboard",
    tags=["Health Dashboard"],
    dependencies=[Depends(require_health_official)],
)

DbSession = Annotated[Session, Depends(get_db)]

# --------------------------------------------------
# Response schemas
# --------------------------------------------------

class DashboardOverview(BaseModel):
    total_reports: int
    reports_today: int
    reports_last_7_days: int
    unique_diseases_reported: int
    generated_at: datetime

class DiseaseCount(BaseModel):
    disease_name: str
    report_count: int

class DiseaseTrendsResponse(BaseModel):
    total_reports: int
    diseases: list[DiseaseCount]

class DailyCaseCount(BaseModel):
    date: str
    report_count: int

class HistoricalCasesResponse(BaseModel):
    days_requested: int
    daily_counts: list[DailyCaseCount]

# --------------------------------------------------
# Helper
# --------------------------------------------------

def _run_query(db: Session, query):
    """Run a dashboard query with consistent database error handling."""
    try:
        return db.execute(query)
    except SQLAlchemyError:
        logger.exception("Dashboard database query failed.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dashboard data is temporarily unavailable.",
        )

# --------------------------------------------------
# GET /dashboard/overview
# --------------------------------------------------

@router.get("/overview", response_model=DashboardOverview)
def get_dashboard_overview(
    db: DbSession,
) -> DashboardOverview:
    """
    Return high-level surveillance counts.

    All counts refer to submitted health reports, not confirmed diagnoses.
    """
    now = datetime.now(timezone.utc)
    today_start = now.replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    week_start = now - timedelta(days=7)

    total_query = select(func.count(HealthReport.__table__.c.id))

    today_query = select(
        func.count(HealthReport.__table__.c.id)
    ).where(HealthReport.__table__.c.created_at >= today_start)

    week_query = select(
        func.count(HealthReport.__table__.c.id)
    ).where(HealthReport.__table__.c.created_at >= week_start)

    diseases_query = select(
        func.count(func.distinct(HealthReport.__table__.c.disease_name))
    ).where(
        HealthReport.__table__.c.disease_name.is_not(None),
        HealthReport.__table__.c.disease_name != "",
    )

    total = _run_query(db, total_query).scalar_one()
    today = _run_query(db, today_query).scalar_one()
    last_7_days = _run_query(db, week_query).scalar_one()
    unique_diseases = _run_query(db, diseases_query).scalar_one()

    return DashboardOverview(
        total_reports=total,
        reports_today=today,
        reports_last_7_days=last_7_days,
        unique_diseases_reported=unique_diseases,
        generated_at=now,
    )