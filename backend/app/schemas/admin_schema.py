from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints


NameText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=2, max_length=100),
]

OrganizationText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=2, max_length=150),
]

DesignationText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=2, max_length=100),
]


class AdminRegistrationRequest(BaseModel):
    """Request to register a user as a health official for verification."""

    model_config = ConfigDict(extra="forbid")

    designation: DesignationText
    organization: OrganizationText
    official_reference: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, min_length=3, max_length=100),
    ] = None


class AdminResponse(BaseModel):
    """Safe admin profile returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    designation: str
    organization: str
    official_reference: str | None = None
    is_verified: bool
    verified_at: datetime | None = None
    verified_by: int | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AdminVerificationRequest(BaseModel):
    """Request from an authorized administrator to verify an official."""

    model_config = ConfigDict(extra="forbid")

    is_verified: bool
    is_active: bool
    notes: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, max_length=1000),
    ] = None


class AdminStatusResponse(BaseModel):
    """Minimal response for official verification status."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    is_verified: bool
    is_active: bool
    verified_at: datetime | None = None
