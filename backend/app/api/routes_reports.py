# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportGeneralTypeIssues=false

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.health_report import HealthReport
from app.models.user import User
from app.api.routes_auth import get_current_user
from app.security.authorization import require_health_official

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/reports",
    tags=["Health Reports"],
)

DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


# --------------------------------------------------
# ENUMS
# --------------------------------------------------

class ReportStatus(str, Enum):
    submitted = "submitted"
    under_review = "under_review"
    verified = "verified"
    rejected = "rejected"


# --------------------------------------------------
# REQUEST AND RESPONSE SCHEMAS
# --------------------------------------------------

class HealthReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    disease_name: str = Field(min_length=2, max_length=100)
    symptoms: list[str] = Field(min_length=1, max_length=30)
    region_id: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)


class HealthReportResponse(BaseModel):
    id: int
    user_id: int
    disease_name: str
    symptoms: list[str]
    region_id: str
    description: str | None
    status: ReportStatus
    created_at: datetime


class ReportStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ReportStatus


class PaginatedReports(BaseModel):
    total: int
    limit: int
    offset: int
    reports: list[HealthReportResponse]


# --------------------------------------------------
# HELPER FUNCTIONS
# --------------------------------------------------

def normalize_text(value: str) -> str:
    return " ".join(value.strip().split())


def report_to_response(report: HealthReport) -> HealthReportResponse:
    return HealthReportResponse(
        id=report.id,
        user_id=report.user_id,
        disease_name=report.disease_name,
        symptoms=report.symptoms,
        region_id=report.region_id,
        description=report.description,
        status=report.status,
        created_at=report.created_at,
    )


def database_error() -> HTTPException:
    logger.exception("Health report database operation failed.")

    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="The health report service is temporarily unavailable.",
    )


# --------------------------------------------------
# SUBMIT A HEALTH REPORT
# POST /reports/
# --------------------------------------------------

@router.post(
    "/",
    response_model=HealthReportResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_health_report(
    request: HealthReportCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> HealthReportResponse:

    disease_name = normalize_text(request.disease_name)
    region_id = normalize_text(request.region_id)

    if len(disease_name) < 2 or not region_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A valid disease name and region are required.",
        )

    symptoms = list(
        dict.fromkeys(
            normalize_text(symptom).lower()
            for symptom in request.symptoms
            if normalize_text(symptom)
        )
    )

    if not symptoms:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one valid symptom is required.",
        )

    if len(symptoms) > 30 or any(
        len(symptom) > 100 for symptom in symptoms
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The symptom list exceeds permitted limits.",
        )

    report = HealthReport(
        user_id=current_user.id,
        disease_name=disease_name,
        symptoms=symptoms,
        region_id=region_id,
        description=(
            normalize_text(request.description)
            if request.description
            else None
        ),
        status=ReportStatus.submitted.value,
        created_at=datetime.now(timezone.utc),
    )

    try:
        db.add(report)
        db.commit()
        db.refresh(report)

        logger.info(
            "Health report created: report_id=%s",
            report.id,
        )

        return report_to_response(report)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The report could not be saved with the supplied data.",
        )

    except SQLAlchemyError:
        db.rollback()
        logger.exception("Failed to create health report.")

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The health report service is temporarily unavailable.",
        )


# --------------------------------------------------
# VIEW MY REPORTS
# GET /reports/my-reports
# --------------------------------------------------

@router.get(
    "/my-reports",
    response_model=PaginatedReports,
)
def get_my_reports(
    db: DbSession,
    current_user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedReports:

    try:
        total = db.scalar(
            select(func.count(HealthReport.__table__.c.id))
            .where(HealthReport.__table__.c.user_id == current_user.id)
        ) or 0

        reports = db.scalars(
            select(HealthReport)
            .where(HealthReport.__table__.c.user_id == current_user.id)
            .order_by(HealthReport.__table__.c.created_at.desc())
            .offset(offset)
            .limit(limit)
        ).all()

        return PaginatedReports(
            total=total,
            limit=limit,
            offset=offset,
            reports=[
                report_to_response(report)
                for report in reports
            ],
        )

    except SQLAlchemyError:
        raise database_error()


# --------------------------------------------------
# VIEW A SPECIFIC REPORT
# GET /reports/{report_id}
# --------------------------------------------------

@router.get(
    "/{report_id}",
    response_model=HealthReportResponse,
)
def get_health_report(
    report_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> HealthReportResponse:

    report = db.get(HealthReport, report_id)

    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Health report not found.",
        )

    # Users can only view their own reports.
    # Health officials can access reports for authorized duties.
    if (
        report.user_id != current_user.id
        and getattr(current_user.role, "value", current_user.role)
        not in {"health_official", "admin"}
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Health report not found.",
        )

    return report_to_response(report)


# --------------------------------------------------
# OFFICIAL SURVEILLANCE REPORT LIST
# GET /reports/
# --------------------------------------------------

@router.get(
    "/",
    response_model=PaginatedReports,
    dependencies=[Depends(require_health_official)],
)
def list_health_reports(
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    report_status: ReportStatus | None = Query(default=None),
    region_id: str | None = Query(default=None, max_length=100),
) -> PaginatedReports:

    filters = []

    if report_status is not None:
        filters.append(HealthReport.__table__.c.status == report_status.value)

    if region_id is not None:
        filters.append(
            HealthReport.__table__.c.region_id == normalize_text(region_id)
        )

    try:
        total = db.scalar(
            select(func.count(HealthReport.__table__.c.id))
            .where(*filters)
        ) or 0

        reports = db.scalars(
            select(HealthReport)
            .where(*filters)
            .order_by(HealthReport.__table__.c.created_at.desc())
            .offset(offset)
            .limit(limit)
        ).all()

        return PaginatedReports(
            total=total,
            limit=limit,
            offset=offset,
            reports=[
                report_to_response(report)
                for report in reports
            ],
        )

    except SQLAlchemyError:
        raise database_error()


# --------------------------------------------------
# UPDATE REPORT STATUS
# PATCH /reports/{report_id}/status
# --------------------------------------------------

@router.patch(
    "/{report_id}/status",
    response_model=HealthReportResponse,
    dependencies=[Depends(require_health_official)],
)
def update_report_status(
    report_id: int,
    request: ReportStatusUpdate,
    db: DbSession,
) -> HealthReportResponse:

    report = db.get(HealthReport, report_id)

    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Health report not found.",
        )

    report.status = request.status.value

    try:
        db.commit()
        db.refresh(report)

        logger.info(
            "Health report status updated: report_id=%s status=%s",
            report.id,
            report.status,
        )

        return report_to_response(report)

    except SQLAlchemyError:
        db.rollback()
        raise database_error()