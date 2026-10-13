# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportGeneralTypeIssues=false

import logging
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.user import User
from app.api.routes_auth import get_current_user
from app.security.authorization import require_admin, require_health_official

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/users",
    tags=["Users"],
)

DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]

password_hash = PasswordHash.recommended()


# --------------------------------------------------
# SCHEMAS
# --------------------------------------------------

class UserProfileResponse(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    role: str
    is_active: bool

class UserProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=2, max_length=100)

class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)

class DeactivateResponse(BaseModel):
    user_id: int
    is_active: bool
    message: str


# --------------------------------------------------
# HELPERS
# --------------------------------------------------

def role_as_string(role: object) -> str:
    return str(getattr(role, "value", role))

def to_profile(user: User) -> UserProfileResponse:
    return UserProfileResponse(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=role_as_string(user.role),
        is_active=user.is_active,
    )

def normalize_name(name: str) -> str:
    return " ".join(name.strip().split())


# --------------------------------------------------
# GET MY PROFILE
# GET /users/me
# --------------------------------------------------

@router.get(
    "/me",
    response_model=UserProfileResponse,
)
def get_my_profile(
    current_user: CurrentUser,
) -> UserProfileResponse:
    return to_profile(current_user)


# --------------------------------------------------
# UPDATE MY PROFILE
# PATCH /users/me
# --------------------------------------------------

@router.patch(
    "/me",
    response_model=UserProfileResponse,
)
def update_my_profile(
    request: UserProfileUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> UserProfileResponse:

    full_name = normalize_name(request.full_name)

    if len(full_name) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Please provide a valid name.",
        )

    current_user.full_name = full_name

    try:
        db.commit()
        db.refresh(current_user)
        return to_profile(current_user)

    except SQLAlchemyError:
        db.rollback()
        logger.exception("Failed to update user profile.")

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Profile update is temporarily unavailable.",
        )


# --------------------------------------------------
# CHANGE MY PASSWORD
# POST /users/me/change-password
# --------------------------------------------------

@router.post(
    "/me/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
)
def change_my_password(
    request: ChangePasswordRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> None:

    try:
        valid_password = password_hash.verify(
            request.current_password,
            current_user.hashed_password,
        )
    except (ValueError, TypeError):
        valid_password = False

    if not valid_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )

    if request.current_password == request.new_password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="New password must differ from the current password.",
        )

    current_user.hashed_password = password_hash.hash(
        request.new_password
    )

    try:
        db.commit()

        # Note: existing JWTs remain valid until expiry unless you
        # implement token revocation or a per-user token version.

    except SQLAlchemyError:
        db.rollback()
        logger.exception("Failed to change user password.")

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Password change is temporarily unavailable.",
        )


# --------------------------------------------------
# VIEW USER PROFILE
# GET /users/{user_id}
# Health officials only
# --------------------------------------------------

@router.get(
    "/{user_id}",
    response_model=UserProfileResponse,
    dependencies=[Depends(require_health_official)],
)
def get_user_profile(
    user_id: int,
    db: DbSession,
) -> UserProfileResponse:

    user = db.scalar(
        select(User).where(User.__table__.c.id == user_id)
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    return to_profile(user)


# --------------------------------------------------
# DEACTIVATE USER
# PATCH /users/{user_id}/deactivate
# Administrator only
# --------------------------------------------------

@router.patch(
    "/{user_id}/deactivate",
    response_model=DeactivateResponse,
    dependencies=[Depends(require_admin)],
)
def deactivate_user(
    user_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> DeactivateResponse:

    if current_user.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Administrators cannot deactivate their own account.",
        )

    user = db.scalar(
        select(User).where(User.__table__.c.id == user_id)
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    if not user.is_active:
        return DeactivateResponse(
            user_id=user.id,
            is_active=False,
            message="Account is already deactivated.",
        )

    user.is_active = False

    try:
        db.commit()

        logger.info(
            "Account deactivated: target_user_id=%s actor_user_id=%s",
            user.id,
            current_user.id,
        )

        return DeactivateResponse(
            user_id=user.id,
            is_active=False,
            message="Account deactivated successfully.",
        )

    except SQLAlchemyError:
        db.rollback()
        logger.exception("Failed to deactivate user account.")

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Account deactivation is temporarily unavailable.",
        )