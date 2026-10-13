from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

# ---------------------------------------
# Enumerations
# ---------------------------------------


class HealthReportStatus(str, Enum):
    PENDING = "pending"
    UNDER_REVIEW = "under_review"
    REVIEWED = "reviewed"
    CLOSED = "closed"


# ---------------------------------------
# Reusable Validation
# ---------------------------------------

SymptomText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=2, max_length=100),
]

RegionCode = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=2, max_length=100),
]

DescriptionText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=5, max_length=2000),
]


# ---------------------------------------
# Health Report Submission
# ---------------------------------------


class HealthReportCreate(BaseModel):
    """Input submitted by a user reporting a health concern."""

    model_config = ConfigDict(extra="forbid")

    symptoms: list[SymptomText] = Field(min_length=1, max_length=30)
    region_id: RegionCode
    description: DescriptionText | None = None

    @field_validator("symptoms")
    @classmethod
    def validate_symptoms(cls, symptoms: list[str]) -> list[str]:
        # Remove duplicate symptoms without changing their order.
        unique_symptoms = list(dict.fromkeys(s.lower() for s in symptoms))

        if not unique_symptoms:
            raise ValueError("At least one symptom is required.")

        return unique_symptoms


# ---------------------------------------
# Health Report Response
# ---------------------------------------


class HealthReportResponse(BaseModel):
    """Health report data returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    disease_name: str | None = None
    symptoms: list[str]
    region_id: str | None = None
    description: str | None = None
    status: HealthReportStatus
    created_at: datetime
    updated_at: datetime


# ---------------------------------------
# Health Report Status Update
# ---------------------------------------


class HealthReportStatusUpdate(BaseModel):
    """Status update requested by an authorized health official."""

    model_config = ConfigDict(extra="forbid")

    status: HealthReportStatus
    review_notes: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=2, max_length=1000),
    ] | None = None


# ---------------------------------------
# Paginated Health Report Response
# ---------------------------------------


class HealthReportListResponse(BaseModel):
    """Paginated health report results."""

    model_config = ConfigDict(extra="forbid")

    items: list[HealthReportResponse]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    pages: int = Field(ge=0)


# ---------------------------------------
# Health Dashboard Summary
# ---------------------------------------


class HealthDashboardSummary(BaseModel):
    """Aggregate statistics for the health surveillance dashboard."""

    model_config = ConfigDict(extra="forbid")

    total_reports: int = Field(ge=0)
    reports_today: int = Field(ge=0)
    pending_reports: int = Field(ge=0)
    reviewed_reports: int = Field(ge=0)
    distinct_reported_diseases: int = Field(ge=0)
    last_updated: datetime

