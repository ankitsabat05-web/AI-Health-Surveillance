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
    model_validator,
)


# ---------------------------------------
# Reusable Validation Types
# ---------------------------------------

FullName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=2,
        max_length=100,
    ),
]

Password = Annotated[
    str,
    StringConstraints(
        min_length=12,
        max_length=128,
    ),
]


# ---------------------------------------
# Base Schema
# ---------------------------------------

class UserSchema(BaseModel):
    """Shared configuration for user-related request schemas."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=False,
    )


# ---------------------------------------
# User Registration
# ---------------------------------------

class UserCreate(UserSchema):
    """Request body for public user registration."""

    full_name: FullName
    email: EmailStr
    password: Password

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        if not any(character.isalpha() for character in value):
            raise ValueError("Full name must contain letters.")

        if any(ord(character) < 32 for character in value):
            raise ValueError("Full name contains invalid characters.")

        return value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Password cannot contain only whitespace.")

        if any(ord(character) < 32 for character in value):
            raise ValueError("Password contains invalid control characters.")

        return value


# ---------------------------------------
# User Login
# ---------------------------------------

class UserLogin(UserSchema):
    """Request body for JSON-based login."""

    email: EmailStr
    password: Annotated[
        str,
        StringConstraints(min_length=1, max_length=128),
    ]

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


# ---------------------------------------
# User Profile Update
# ---------------------------------------

class UserUpdate(UserSchema):
    """Allow users to update permitted profile fields."""

    full_name: FullName | None = None
    email: EmailStr | None = None

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str | None) -> str | None:
        if value is None:
            return None

        if not any(character.isalpha() for character in value):
            raise ValueError("Full name must contain letters.")

        if any(ord(character) < 32 for character in value):
            raise ValueError("Full name contains invalid characters.")

        return value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr | None) -> str | None:
        if value is None:
            return None

        return str(value).strip().lower()

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> "UserUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided.")

        return self


# ---------------------------------------
# Password Change
# ---------------------------------------

class PasswordChange(UserSchema):
    """Request body for changing the authenticated user's password."""

    current_password: Annotated[
        str,
        StringConstraints(min_length=1, max_length=128),
    ]

    new_password: Password

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("New password cannot contain only whitespace.")

        if any(ord(character) < 32 for character in value):
            raise ValueError("Password contains invalid control characters.")

        return value

    @model_validator(mode="after")
    def ensure_password_changed(self) -> "PasswordChange":
        if self.current_password == self.new_password:
            raise ValueError("New password must differ from the current password.")

        return self


# ---------------------------------------
# Public User Response
# ---------------------------------------

class UserResponse(BaseModel):
    """Safe user representation returned by the API."""

    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
    )

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
    """Paginated user-list response for authorized administrators."""

    items: list[UserResponse]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    pages: int = Field(ge=0)


# ---------------------------------------
# Account Status Response
# ---------------------------------------

class UserStatusResponse(BaseModel):
    """Response after an authorized account-status change."""

    user_id: int
    is_active: bool
    message: str


# ---------------------------------------
# Password Change Response
# ---------------------------------------

class PasswordChangeResponse(BaseModel):
    """Response after a successful password change."""

    message: str
