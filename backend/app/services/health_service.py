from __future__ import annotations

import logging
from math import ceil

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.health_report import HealthReport
from app.models.user import User
from app.schemas.health_schema import HealthReportCreate, HealthReportStatus

logger = logging.getLogger("health_surveillance.health_service")


# ---------------------------------------
# Helpers
# ---------------------------------------

def get_report_or_404(db: Session, report_id: int) -> HealthReport:
    """Retrieve a health report or return HTTP 404."""
    report = db.get(HealthReport, report_id)

    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Health report not found.",
        )

    return report


def _commit_changes(db: Session, operation: str) -> None:
    """Commit database changes with safe error handling."""
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.error("Database operation failed: %s", operation)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Health reporting service is temporarily unavailable.",
        ) from None


# ---------------------------------------
# Submit Health Report
# ---------------------------------------

def submit_health_report(
    db: Session,
    *,
    current_user: User,
    report_data: HealthReportCreate,
) -> HealthReport:
    """Submit a health concern for review."""
    report = HealthReport(
        user_id=current_user.id,
        symptoms=report_data.symptoms,
        region_id=report_data.region_id,
        description=report_data.description,
        disease_name=None,
        status=HealthReportStatus.PENDING.value,
    )

    try:
        db.add(report)
        db.commit()
        db.refresh(report)
        return report
    except SQLAlchemyError:
        db.rollback()
        logger.error("Database operation failed: submit_health_report")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to submit the health report at this time.",
        ) from None


# ---------------------------------------
# Retrieve One Report
# ---------------------------------------

def get_health_report(
    db: Session,
    *,
    report_id: int,
    current_user: User,
) -> HealthReport:
    """Retrieve a report owned by the current user."""
    report = db.scalar(
        select(HealthReport).where(
            HealthReport.id == report_id,
            HealthReport.user_id == current_user.id,
        )
    )

    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Health report not found.",
        )

    return report


# ---------------------------------------
# List Current User's Reports
# ---------------------------------------

def list_my_health_reports(
    db: Session,
    *,
    current_user: User,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Return the current user's health reports with pagination."""
    if page < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Page must be at least 1.",
        )

    if not 1 <= page_size <= 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Page size must be between 1 and 100.",
        )

    base_filter = HealthReport.user_id == current_user.id

    total = db.scalar(
        select(func.count(HealthReport.id)).where(base_filter)
    ) or 0

    reports = db.scalars(
        select(HealthReport)
        .where(base_filter)
        .order_by(HealthReport.created_at.desc(), HealthReport.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return {
        "items": list(reports),
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": ceil(total / page_size) if total else 0,
    }


# ---------------------------------------
# List Reports for Authorized Officials
# ---------------------------------------

def list_health_reports_for_officials(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    report_status: HealthReportStatus | None = None,
    region_id: str | None = None,
) -> dict:
    """Return paginated reports for an API endpoint protected by official authorization."""
    if page < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Page must be at least 1.",
        )

    if not 1 <= page_size <= 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Page size must be between 1 and 100.",
        )

    statement = select(HealthReport)
    count_statement = select(func.count(HealthReport.id))

    if report_status is not None:
        status_value = report_status.value
        statement = statement.where(HealthReport.status == status_value)
        count_statement = count_statement.where(HealthReport.status == status_value)

    if region_id is not None:
        normalized_region = region_id.strip()
        statement = statement.where(HealthReport.region_id == normalized_region)
        count_statement = count_statement.where(HealthReport.region_id == normalized_region)

    total = db.scalar(count_statement) or 0

    reports = db.scalars(
        statement
        .order_by(HealthReport.created_at.desc(), HealthReport.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return {
        "items": list(reports),
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": ceil(total / page_size) if total else 0,
    }


# ---------------------------------------
# Update Report Status
# ---------------------------------------

def update_health_report_status(
    db: Session,
    *,
    report_id: int,
    new_status: HealthReportStatus,
    current_user: User,
    review_notes: str | None = None,
) -> HealthReport:
    """Update report status after authorized review."""
    report = get_report_or_404(db, report_id)

    allowed_transitions = {
        HealthReportStatus.PENDING.value: {
            HealthReportStatus.UNDER_REVIEW.value,
            HealthReportStatus.CLOSED.value,
        },
        HealthReportStatus.UNDER_REVIEW.value: {
            HealthReportStatus.REVIEWED.value,
            HealthReportStatus.CLOSED.value,
        },
        HealthReportStatus.REVIEWED.value: {
            HealthReportStatus.CLOSED.value,
        },
        HealthReportStatus.CLOSED.value: set(),
    }

    target_status = new_status.value

    if target_status == report.status:
        return report

    permitted = allowed_transitions.get(report.status, set())

    if target_status not in permitted:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This health-report status transition is not permitted.",
        )

    report.status = target_status

    _commit_changes(db, "update_health_report_status")
    db.refresh(report)

    return report


# ---------------------------------------
# Aggregate Report Statistics
# ---------------------------------------

def get_health_report_summary(
    db: Session,
    *,
    region_id: str | None = None,
) -> dict[str, int]:
    """Return aggregate report counts for an authorized dashboard."""
    filters = []

    if region_id is not None:
        filters.append(HealthReport.region_id == region_id.strip())

    total_reports = db.scalar(
        select(func.count(HealthReport.id)).where(*filters)
    ) or 0

    pending_reports = db.scalar(
        select(func.count(HealthReport.id)).where(
            *filters,
            HealthReport.status == HealthReportStatus.PENDING.value,
        )
    ) or 0

    reviewed_reports = db.scalar(
        select(func.count(HealthReport.id)).where(
            *filters,
            HealthReport.status == HealthReportStatus.REVIEWED.value,
        )
    ) or 0

    return {
        "total_reports": total_reports,
        "pending_reports": pending_reports,
        "reviewed_reports": reviewed_reports,
    }
