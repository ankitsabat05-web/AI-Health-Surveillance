# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportGeneralTypeIssues=false

# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportGeneralTypeIssues=false

import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.database.database import get_db
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

# --------------------------------------------------
# SECURITY CONFIGURATION
# --------------------------------------------------

JWT_SECRET_KEY = settings.SECRET_KEY.get_secret_value()
JWT_ALGORITHM = "HS256"

password_hash = PasswordHash.recommended()

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login"
)

DbSession = Annotated[Session, Depends(get_db)]
BearerToken = Annotated[str, Depends(oauth2_scheme)]


# --------------------------------------------------
# REQUEST AND RESPONSE SCHEMAS
# --------------------------------------------------

class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)


class UserResponse(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    role: str
    is_active: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


# --------------------------------------------------
# HELPER FUNCTIONS
# --------------------------------------------------

def _role_as_string(role: object) -> str:
    """Convert either a string or Enum role into a string."""
    return str(getattr(role, "value", role))


def _to_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=_role_as_string(user.role),
        is_active=user.is_active,
    )


def create_access_token(user_id: int) -> tuple[str, int]:
    """Generate a short-lived JWT for an authenticated user."""
    expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    now = datetime.now(timezone.utc)

    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }

    token = jwt.encode(
        payload,
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )

    return token, expires_in


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )


# --------------------------------------------------
# AUTHENTICATE THE CURRENT USER
# --------------------------------------------------

def get_current_user(
    token: BearerToken,
    db: DbSession,
) -> User:
    """Verify the token and retrieve the current active user."""
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            options={
                "require_sub": True,
                "require_exp": True,
            },
        )

        subject = payload.get("sub")

        if not isinstance(subject, str) or not subject.isdigit():
            raise _unauthorized()

        user_id = int(subject)

    except (JWTError, ValueError, TypeError):
        raise _unauthorized()

    try:
        user = db.scalar(
            select(User).where(User.__table__.c.id == user_id)
        )
    except SQLAlchemyError:
        logger.exception("Database error during authentication.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is temporarily unavailable.",
        )

    if user is None or not user.is_active:
        raise _unauthorized()

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


# --------------------------------------------------
# REGISTER A NORMAL USER
# --------------------------------------------------

@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_user(
    request: RegisterRequest,
    db: DbSession,
) -> UserResponse:

    full_name = request.full_name.strip()
    email = str(request.email).strip().lower()

    if len(full_name) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Please provide a valid full name.",
        )

    try:
        existing_user = db.scalar(
            select(User.__table__.c.id).where(User.__table__.c.email == email)
        )

        if existing_user is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists.",
            )

        user = User(
            **{
                "full_name": full_name,
                "email": email,
                "hashed_password": password_hash.hash(request.password),
                "role": "user",
                "is_active": True,
            }
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        return _to_user_response(user)

    except HTTPException:
        db.rollback()
        raise

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    except SQLAlchemyError:
        db.rollback()
        logger.exception("Database error during registration.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Registration is temporarily unavailable.",
        )


# --------------------------------------------------
# LOGIN
# --------------------------------------------------

@router.post(
    "/login",
    response_model=TokenResponse,
)
def login_user(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DbSession,
) -> TokenResponse:

    email = form.username.strip().lower()

    try:
        user = db.scalar(
            select(User).where(User.__table__.c.email == email)
        )
    except SQLAlchemyError:
        logger.exception("Database error during login.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Login is temporarily unavailable.",
        )

    # Never reveal whether the account exists.
    if user is None:
        raise _unauthorized()

    try:
        password_valid = password_hash.verify(
            form.password,
            user.hashed_password,
        )
    except (ValueError, TypeError):
        logger.error("Invalid password hash format for a stored account.")
        raise _unauthorized()

    if not password_valid or not user.is_active:
        raise _unauthorized()

    token, expires_in = create_access_token(user.id)

    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
    )


# --------------------------------------------------
# CURRENT USER PROFILE
# --------------------------------------------------

@router.get(
    "/me",
    response_model=UserResponse,
)
def get_my_profile(
    current_user: CurrentUser,
) -> UserResponse:
    return _to_user_response(current_user)