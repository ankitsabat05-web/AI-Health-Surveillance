from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.admin import Admin
from app.models.user import User
from app.security.authentication import get_current_user

# ---------------------------------------
# Role Configuration
# ---------------------------------------

ROLE_USER = "user"
ROLE_HEALTH_OFFICIAL = "health_official"
ROLE_ADMIN = "admin"

# ---------------------------------------
# Shared Dependencies
# ---------------------------------------

CurrentUser = Annotated[User, Depends(get_current_user)]
DatabaseSession = Annotated[Session, Depends(get_db)]


def _get_role(user: User) -> str:
    """Return the normalized role stored on the user record."""
    role = getattr(user.role, "value", user.role)
    return str(role).strip().lower()


def _forbidden(
    message: str = "You do not have permission to access this resource."
) -> HTTPException:
    """Create a consistent authorization error."""
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=message,
    )


# ---------------------------------------
# Ordinary User Authorization
# ---------------------------------------


def require_user(current_user: CurrentUser) -> User:
    """Allow an active ordinary user."""
    if _get_role(current_user) != ROLE_USER:
        raise _forbidden("This endpoint is available to ordinary users only.")

    return current_user


# ---------------------------------------
# Verified Health Official Authorization
# ---------------------------------------


def require_health_official(
    current_user: CurrentUser,
    db: DatabaseSession,
) -> User:
    """
    Allow a verified, active health official.

    Administrators must use the separate admin dependency.
    """
    if _get_role(current_user) != ROLE_HEALTH_OFFICIAL:
        raise _forbidden("Health-official access is required.")

    official = db.scalar(
        select(Admin).where(
            Admin.user_id == current_user.id,
            Admin.is_verified.is_(True),
            Admin.is_active.is_(True),
        )
    )

    if official is None:
        raise _forbidden(
            "Your health-official account is not verified or active."
        )

    return current_user


# ---------------------------------------
# Administrator Authorization
# ---------------------------------------


def require_admin(
    current_user: CurrentUser,
    db: DatabaseSession,
) -> User:
    """
    Allow an active administrator whose official record is verified.

    An administrator's permissions are derived from the database,
    not from user-supplied request data.
    """
    if _get_role(current_user) != ROLE_ADMIN:
        raise _forbidden("Administrator access is required.")

    admin_record = db.scalar(
        select(Admin).where(
            Admin.user_id == current_user.id,
            Admin.is_verified.is_(True),
            Admin.is_active.is_(True),
        )
    )

    if admin_record is None:
        raise _forbidden(
            "Your administrator account is not verified or active."
        )

    return current_user


# ---------------------------------------
# Health Official OR Administrator
# ---------------------------------------


def require_health_authority(
    current_user: CurrentUser,
    db: DatabaseSession,
) -> User:
    """
    Allow either a verified health official or a verified administrator.

    Use this for shared dashboards only when both roles are permitted
    to access the relevant data.
    """
    role = _get_role(current_user)

    if role not in {ROLE_HEALTH_OFFICIAL, ROLE_ADMIN}:
        raise _forbidden("Authorized health authority access is required.")

    authority = db.scalar(
        select(Admin).where(
            Admin.user_id == current_user.id,
            Admin.is_verified.is_(True),
            Admin.is_active.is_(True),
        )
    )

    if authority is None:
        raise _forbidden(
            "Your official account is not verified or active."
        )

    return current_user

