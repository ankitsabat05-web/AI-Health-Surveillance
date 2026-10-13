# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportGeneralTypeIssues=false

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.alert import Alert
from app.security.authorization import require_health_official

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/alerts",
    tags=["Health Surveillance Alerts"],
    dependencies=[Depends(require_health_official)],
)

DbSession = Annotated[Session, Depends(get_db)]

Severity = Literal["low", "moderate", "high", "critical"]
AlertStatus = Literal["new", "acknowledged", "resolved"]


# ============================================================
# RESPONSE SCHEMAS
# ============================================================

class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    title: str
    description: str
    severity: Severity
    status: AlertStatus
    disease_name: str | None = None
    region_id: str | None = None
    created_at: datetime
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None


class AlertListResponse(BaseModel):
    items: list[AlertResponse]
    total: int
    limit: int
    offset: int


class AlertStatusResponse(BaseModel):
    id: int
    status: AlertStatus
    message: str


# ============================================================
# HELPERS
# ============================================================

def _get_official_id(official: object) -> str:
    """
    Extract the ID from the authenticated official returned by
    require_health_official.

    Adapt this helper if your user model uses a different ID field.
    Never accept the acknowledging official's ID from the request body.
    """
    official_id = getattr(official, "id", None)

    if official_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated official identity is unavailable.",
        )

    return str(official_id)


def _get_alert_or_404(db: Session, alert_id: int) -> Alert:
    alert = db.get(Alert, alert_id)

    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found.",
        )

    return alert


# ============================================================
# LIST ALERTS
# ============================================================

@router.get(
    "",
    response_model=AlertListResponse,
)
def list_alerts(
    db: DbSession,
    severity: Severity | None = Query(default=None),
    alert_status: AlertStatus | None = Query(
        default=None,
        alias="status",
    ),
    disease_name: str | None = Query(
        default=None,
        min_length=2,
        max_length=100,
    ),
    region_id: str | None = Query(
        default=None,
        min_length=1,
        max_length=100,
    ),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=1_000_000),
) -> AlertListResponse:
    """Return paginated alerts for authorized health officials."""

    try:
        conditions = []

        if severity is not None:
            conditions.append(Alert.severity == severity)

        if alert_status is not None:
            conditions.append(Alert.status == alert_status)

        if disease_name is not None:
            normalized_disease = disease_name.strip()

            if not normalized_disease:
                raise HTTPException(
                    status_code=422,
                    detail="disease_name cannot be empty.",
                )

            conditions.append(
                Alert.disease_name.ilike(normalized_disease)
            )

        if region_id is not None:
            normalized_region = region_id.strip()

            if not normalized_region:
                raise HTTPException(
                    status_code=422,
                    detail="region_id cannot be empty.",
                )

            conditions.append(Alert.region_id == normalized_region)

        count_query = select(Alert.__table__.c.id)

        if conditions:
            count_query = count_query.where(*conditions)

        total = len(db.scalars(count_query).all())

        items_query = select(Alert)

        if conditions:
            items_query = items_query.where(*conditions)

        items_query = (
            items_query
            .order_by(
                Alert.__table__.c.created_at.desc(),
                Alert.__table__.c.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )

        items = list(db.scalars(items_query).all())

        return AlertListResponse(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
        )

    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        logger.exception("Unable to retrieve health alerts.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Alerts are temporarily unavailable.",
        ) from exc


# ============================================================
# GET A SINGLE ALERT
# ============================================================

@router.get(
    "/{alert_id}",
    response_model=AlertResponse,
)
def get_alert(
    alert_id: int,
    db: DbSession,
) -> Alert:
    """Retrieve an individual alert by its ID."""

    try:
        return _get_alert_or_404(db, alert_id)

    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        logger.exception("Unable to retrieve alert.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The alert is temporarily unavailable.",
        ) from exc


# ============================================================
# ACKNOWLEDGE AN ALERT
# ============================================================

@router.post(
    "/{alert_id}/acknowledge",
    response_model=AlertStatusResponse,
)
def acknowledge_alert(
    alert_id: int,
    db: DbSession,
    official: Annotated[object, Depends(require_health_official)],
) -> AlertStatusResponse:
    """
    Mark an alert as acknowledged by the authenticated official.

    Acknowledgement means an official has taken responsibility for
    reviewing the alert; it does not mean an outbreak is confirmed.
    """

    official_id = _get_official_id(official)

    try:
        # Lock the row where supported, reducing conflicting updates.
        query = (
            select(Alert)
            .where(Alert.id == alert_id)
            .with_for_update()
        )
        alert = db.scalars(query).first()

        if alert is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Alert not found.",
            )

        if alert.status == "resolved":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A resolved alert cannot be acknowledged.",
            )

        if alert.status == "new":
            alert.status = "acknowledged"
            alert.acknowledged_at = datetime.now(timezone.utc)
            alert.acknowledged_by = official_id
            db.commit()
            db.refresh(alert)

        return AlertStatusResponse(
            id=alert.id,
            status=alert.status,
            message="Alert acknowledged for official review.",
        )

    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Unable to acknowledge alert.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The alert could not be acknowledged.",
        ) from exc


# ============================================================
# RESOLVE AN ALERT
# ============================================================

@router.post(
    "/{alert_id}/resolve",
    response_model=AlertStatusResponse,
)
def resolve_alert(
    alert_id: int,
    db: DbSession,
    official: Annotated[object, Depends(require_health_official)],
) -> AlertStatusResponse:
    """
    Mark an alert as resolved after official review.

    In a production system, resolution should also record an audit
    event and the official's resolution rationale.
    """

    _get_official_id(official)

    try:
        query = (
            select(Alert)
            .where(Alert.id == alert_id)
            .with_for_update()
        )
        alert = db.scalars(query).first()

        if alert is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Alert not found.",
            )

        if alert.status == "resolved":
            return AlertStatusResponse(
                id=alert.id,
                status="resolved",
                message="Alert is already resolved.",
            )

        alert.status = "resolved"
        db.commit()
        db.refresh(alert)

        return AlertStatusResponse(
            id=alert.id,
            status="resolved",
            message="Alert marked as resolved.",
        )

    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Unable to resolve alert.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The alert could not be resolved.",
        ) from exc