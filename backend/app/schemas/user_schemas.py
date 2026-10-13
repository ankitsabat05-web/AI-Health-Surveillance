from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
)

# ---------------------------------------
# Reusable Validation Types
# ---------------------------------------

FullName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=2, max_length=100),
]

Password = Annotated[
    str,
    StringConstraints(min_length=12, max_length=128),
]


# ---------------------------------------
# User Registration
# ---------------------------------------


class UserCreate(BaseModel):
    """Validate registration details for a standard user."""

    model_config = ConfigDict(extra="forbid")

    full_name: FullName
    email: EmailStr
    password: Password

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


# ---------------------------------------
# User Login
# ---------------------------------------


class UserLogin(BaseModel):
    """Validate user login credentials."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: Annotated[
        str,
        StringConstraints(min_length=1, max_length=128),
    ]

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


# ---------------------------------------
# User Profile Update
# ---------------------------------------


class UserUpdate(BaseModel):
    """Allow users to update their own basic profile information."""

    model_config = ConfigDict(extra="forbid")

    full_name: FullName | None = None
    email: EmailStr | None = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        return value.strip().lower() if value is not None else None


# ---------------------------------------
# Password Change
# ---------------------------------------


class PasswordChange(BaseModel):
    """Validate a password-change request."""

    model_config = ConfigDict(extra="forbid")

    current_password: Annotated[
        str,
        StringConstraints(min_length=1, max_length=128),
    ]

    new_password: Password

    @field_validator("new_password")
    @classmethod
    def reject_whitespace_only_password(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("The new password cannot contain only whitespace.")
        return value


# ---------------------------------------
# Safe User Response
# ---------------------------------------


class UserResponse(BaseModel):
    """Return public profile information without credentials."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: EmailStr
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------
# User List Response
# ---------------------------------------


class UserListResponse(BaseModel):
    """Paginated user results for authorized administration endpoints."""

    model_config = ConfigDict(extra="forbid")

    items: list[UserResponse]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    pages: int = Field(ge=0)

