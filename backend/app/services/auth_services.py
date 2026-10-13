from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import secrets

from fastapi import HTTPException, status
from jose import jwt
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.user import User

logger = logging.getLogger("health_surveillance.auth")

ALGORITHM = "HS256"
password_hasher = PasswordHash.recommended()


# ---------------------------------------
# Password Utilities
# ---------------------------------------

def hash_password(password: str) -> str:
    """Hash a password using the configured secure password hasher."""
    if not isinstance(password, str) or not password:
        raise ValueError("A valid password is required.")

    return password_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its stored hash."""
    try:
        return password_hasher.verify(plain_password, hashed_password)
    except (ValueError, TypeError):
        return False


# ---------------------------------------
# JWT Utilities
# ---------------------------------------

def create_access_token(
    user_id: int,
    *,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a short-lived JWT for an authenticated user."""
    if user_id <= 0:
        raise ValueError("user_id must be positive.")

    now = datetime.now(timezone.utc)
    lifetime = expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    if lifetime.total_seconds() <= 0:
        raise ValueError("Token lifetime must be positive.")

    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + lifetime,
        "jti": secrets.token_urlsafe(16),
    }

    return jwt.encode(
        payload,
        settings.SECRET_KEY.get_secret_value(),
        algorithm=ALGORITHM,
    )


# ---------------------------------------
# User Registration
# ---------------------------------------

def register_user(
    db: Session,
    *,
    full_name: str,
    email: str,
    password: str,
) -> User:
    """Register an ordinary user."""
    normalized_email = email.strip().lower()

    existing_user = db.scalar(
        select(User.id).where(User.email == normalized_email)
    )

    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Unable to register with these details.",
        )

    user = User(
        full_name=full_name.strip(),
        email=normalized_email,
        hashed_password=hash_password(password),
        role="user",
        is_active=True,
    )

    try:
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Unable to register with these details.",
        ) from None
    except SQLAlchemyError:
        db.rollback()
        logger.error("Database error during user registration.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Registration is temporarily unavailable.",
        ) from None


# ---------------------------------------
# User Authentication
# ---------------------------------------

def authenticate_user(
    db: Session,
    *,
    email: str,
    password: str,
) -> User | None:
    """Verify login credentials."""
    normalized_email = email.strip().lower()

    user = db.scalar(
        select(User).where(User.email == normalized_email)
    )

    if user is None:
        return None

    if not verify_password(password, user.hashed_password):
        return None

    if not user.is_active:
        return None

    return user


def login_user(
    db: Session,
    *,
    email: str,
    password: str,
) -> dict[str, str]:
    """Authenticate a user and return a short-lived access token."""
    user = authenticate_user(
        db,
        email=email,
        password=password,
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {
        "access_token": create_access_token(user.id),
        "token_type": "bearer",
    }


# ---------------------------------------
# Password Change
# ---------------------------------------

def change_user_password(
    db: Session,
    *,
    user: User,
    current_password: str,
    new_password: str,
) -> None:
    """Change the authenticated user's password after verifying the old one."""
    if not verify_password(current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to change password with the supplied credentials.",
        )

    if current_password == new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Choose a different new password.",
        )

    user.hashed_password = hash_password(new_password)

    try:
        db.add(user)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.error("Database error during password change.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Password change is temporarily unavailable.",
        ) from None