from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database.database import get_db
from app.models.user import User

# ---------------------------------------
# Authentication Configuration
# ---------------------------------------

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
    auto_error=False,
)

ALGORITHM = "HS256"

# ---------------------------------------
# Authentication Exceptions
# ---------------------------------------


def authentication_error() -> HTTPException:
    """Return a consistent authentication error."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )


# ---------------------------------------
# Get Authenticated User
# ---------------------------------------


def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """
    Validate the JWT and retrieve the corresponding active user.

    The token must contain a valid subject (`sub`) identifying the user
    and a valid expiration (`exp`).
    """
    if not token:
        raise authentication_error()

    try:
        secret_key = settings.SECRET_KEY.get_secret_value()

        payload = jwt.decode(
            token,
            secret_key,
            algorithms=[ALGORITHM],
            options={
                "require_exp": True,
                "require_sub": True,
            },
        )

        subject = payload.get("sub")

        if not isinstance(subject, str) or not subject.isdigit():
            raise authentication_error()

        user_id = int(subject)
    except (JWTError, ValueError, TypeError):
        raise authentication_error() from None

    user = db.scalar(select(User).where(User.id == user_id))

    if user is None or not user.is_active:
        raise authentication_error()

    return user


# ---------------------------------------
# Current User Dependency
# ---------------------------------------

CurrentUser = Annotated[User, Depends(get_current_user)]

# ---------------------------------------
# Optional Authentication
# ---------------------------------------


def get_optional_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User | None:
    """
    Return the authenticated user when a valid token is supplied.

    Return None when no token is supplied. Invalid supplied tokens
    still produce an authentication error.
    """
    if not token:
        return None

    return get_current_user(token=token, db=db)


OptionalCurrentUser = Annotated[
    User | None,
    Depends(get_optional_current_user),
]
