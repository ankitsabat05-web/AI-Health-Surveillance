from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# --------------------------------
# Reusable Validation
# --------------------------------

DiseaseName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=2, max_length=100),
]

DiseaseCategory = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=2, max_length=100),
]

DiseaseDescription = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=5, max_length=2000),
]

# --------------------------------
# Base Disease Schema
# --------------------------------


class DiseaseBase(BaseModel):
    """Shared fields for disease creation and updates."""

    name: DiseaseName
    description: DiseaseDescription | None = None
    category: DiseaseCategory | None = None


# --------------------------------
# Disease Creation Schema
# --------------------------------


class DiseaseCreate(DiseaseBase):
    """Validated input for adding a disease to the monitoring catalogue."""

    model_config = ConfigDict(extra="forbid")


# --------------------------------
# Disease Update Schema
# --------------------------------


class DiseaseUpdate(BaseModel):
    """Partial updates to an existing disease."""

    model_config = ConfigDict(extra="forbid")

    name: DiseaseName | None = None
    description: DiseaseDescription | None = None
    category: DiseaseCategory | None = None
    is_monitored: bool | None = None

    def validate_update(self) -> None:
        """Reject empty updates and explicit nulls for required fields."""
        changes = self.model_dump(exclude_unset=True)

        if not changes:
            raise ValueError("At least one field must be provided.")

        if "name" in changes and changes["name"] is None:
            raise ValueError("Disease name cannot be null.")

        if "is_monitored" in changes and changes["is_monitored"] is None:
            raise ValueError("Monitoring status cannot be null.")


# --------------------------------
# Disease Response Schema
# --------------------------------


class DiseaseResponse(DiseaseBase):
    """Safe disease record returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    is_monitored: bool
    created_at: datetime


# --------------------------------
# Disease List Response Schema
# --------------------------------


class DiseaseListResponse(BaseModel):
    """Paginated list of diseases."""

    model_config = ConfigDict(extra="forbid")

    items: list[DiseaseResponse]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    pages: int = Field(ge=0)