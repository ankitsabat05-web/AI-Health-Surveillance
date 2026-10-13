from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# -----------------------------
# Enumerations
# -----------------------------


class AlertSeverity(str, Enum):
    LOW = "low"
    WATCH = "watch"
    ELEVATED = "elevated"
    HIGH = "high"
    CRITICAL = "critical"


class AlertStatus(str, Enum):
    OPEN = "open"
    UNDER_REVIEW = "under_review"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class AlertType(str, Enum):
    POTENTIAL_OUTBREAK = "potential_outbreak"
    REGIONAL_HOTSPOT = "regional_hotspot"
    UNUSUAL_INCREASE = "unusual_increase"
    ANOMALY = "anomaly"
    HIGH_RISK = "high_risk"


# -----------------------------
# Reusable Validation
# -----------------------------

AlertTitle = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=3, max_length=200),
]

AlertMessage = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=5, max_length=5000),
]

ReviewNotes = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2000),
]


# -----------------------------
# Alert Creation Schema
# -----------------------------


class AlertCreate(BaseModel):
    """Validated data for creating an alert internally."""

    model_config = ConfigDict(extra="forbid")

    disease_id: int | None = Field(default=None, ge=1)
    location_id: int | None = Field(default=None, ge=1)

    alert_type: AlertType
    severity: AlertSeverity = AlertSeverity.WATCH

    title: AlertTitle
    message: AlertMessage

    supporting_data: dict[str, object] = Field(default_factory=dict)


# -----------------------------
# Alert Response Schema
# -----------------------------


class AlertResponse(BaseModel):
    """Safe alert data returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    disease_id: int | None = None
    location_id: int | None = None

    alert_type: AlertType
    severity: AlertSeverity

    title: str
    message: str
    supporting_data: dict[str, object]

    status: AlertStatus

    reviewed_by: int | None = None
    review_notes: str | None = None

    created_at: datetime
    reviewed_at: datetime | None = None
    resolved_at: datetime | None = None


# -----------------------------
# Alert Review Schema
# -----------------------------


class AlertReviewRequest(BaseModel):
    """Request for an authorized official to review an alert."""

    model_config = ConfigDict(extra="forbid")

    status: AlertStatus
    review_notes: ReviewNotes | None = None


# -----------------------------
# Alert List / Filtering Schema
# -----------------------------


class AlertListQuery(BaseModel):
    """Pagination and filtering options for alert lists."""

    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1, le=100000)
    page_size: int = Field(default=20, ge=1, le=100)

    severity: AlertSeverity | None = None
    status: AlertStatus | None = None
    alert_type: AlertType | None = None
    disease_id: int | None = Field(default=None, ge=1)
    location_id: int | None = Field(default=None, ge=1)


class AlertListResponse(BaseModel):
    """Paginated alert results."""

    items: list[AlertResponse]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    pages: int = Field(ge=0)

