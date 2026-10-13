from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, time, timedelta, timezone
from math import ceil
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException, status


# ---------------------------------------
# Constants
# ---------------------------------------

DEFAULT_TIMEZONE = "Asia/Kolkata"
DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
MAX_TEXT_LENGTH = 2000


# ---------------------------------------
# Date and Time Utilities
# ---------------------------------------

def utc_now() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def get_timezone(timezone_name: str = DEFAULT_TIMEZONE) -> ZoneInfo:
    """Return a validated timezone."""
    try:
        return ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid timezone.",
        ) from None


def get_local_date(timezone_name: str = DEFAULT_TIMEZONE) -> date:
    """Return today's date in the requested timezone."""
    return utc_now().astimezone(get_timezone(timezone_name)).date()


def get_date_range(
    start_date: date,
    end_date: date,
    *,
    max_days: int = 366,
) -> tuple[date, date]:
    """Validate and return an inclusive date range."""
    if start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Start date must not be after end date.",
        )

    if max_days < 1 or (end_date - start_date).days + 1 > max_days:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Date range cannot exceed {max_days} days.",
        )

    return start_date, end_date


def get_day_boundaries(
    selected_date: date,
    timezone_name: str = DEFAULT_TIMEZONE,
) -> tuple[datetime, datetime]:
    """Return timezone-aware start and exclusive end boundaries for a local calendar day."""
    tz = get_timezone(timezone_name)

    start = datetime.combine(
        selected_date,
        time.min,
        tzinfo=tz,
    )

    end_exclusive = datetime.combine(
        selected_date + timedelta(days=1),
        time.min,
        tzinfo=tz,
    )

    return start, end_exclusive


# ---------------------------------------
# Pagination Utilities
# ---------------------------------------

def validate_pagination(
    page: int = DEFAULT_PAGE,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> tuple[int, int]:
    """Validate pagination parameters and enforce an upper limit."""
    if page < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Page must be at least 1.",
        )

    if not 1 <= page_size <= MAX_PAGE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Page size must be between 1 and {MAX_PAGE_SIZE}.",
        )

    return page, page_size


def get_pagination_metadata(
    total: int,
    page: int,
    page_size: int,
) -> dict[str, int]:
    """Generate metadata for a paginated API response."""
    if total < 0:
        raise ValueError("Total cannot be negative.")

    validate_pagination(page, page_size)

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": ceil(total / page_size) if total else 0,
    }


def get_offset(page: int, page_size: int) -> int:
    """Calculate a database pagination offset."""
    validate_pagination(page, page_size)
    return (page - 1) * page_size


# ---------------------------------------
# Text Utilities
# ---------------------------------------

def normalize_text(
    value: str,
    *,
    max_length: int = MAX_TEXT_LENGTH,
) -> str:
    """Normalize Unicode and whitespace for ordinary text fields."""
    if not isinstance(value, str):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Text value must be a string.",
        )

    normalized = unicodedata.normalize("NFC", value)
    normalized = " ".join(normalized.split())

    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Text value cannot be empty.",
        )

    if len(normalized) > max_length:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Text cannot exceed {max_length} characters.",
        )

    return normalized


def normalize_email(email: str) -> str:
    """Normalize an email address for consistent account lookups."""
    if not isinstance(email, str):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid email address.",
        )

    normalized = email.strip().lower()

    if not normalized or len(normalized) > 254:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid email address.",
        )

    return normalized


def normalize_identifier(
    value: str,
    *,
    max_length: int = 100,
) -> str:
    """Validate a simple identifier such as a region code."""
    normalized = normalize_text(value, max_length=max_length)

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", normalized):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Identifier contains unsupported characters.",
        )

    return normalized


# ---------------------------------------
# Collection Utilities
# ---------------------------------------

def unique_strings(
    values: list[str],
    *,
    case_insensitive: bool = True,
    max_items: int = 100,
) -> list[str]:
    """Remove duplicate strings while preserving their original order."""
    if len(values) > max_items:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"No more than {max_items} items are allowed.",
        )

    result: list[str] = []
    seen: set[str] = set()

    for value in values:
        normalized = normalize_text(value)
        comparison_key = normalized.casefold() if case_insensitive else normalized

        if comparison_key not in seen:
            seen.add(comparison_key)
            result.append(normalized)

    return result


# ---------------------------------------
# Response Utilities
# ---------------------------------------

def success_response(message: str, data: Any = None) -> dict[str, Any]:
    """Create a consistent success response."""
    return {
        "success": True,
        "message": normalize_text(message, max_length=250),
        "data": data,
    }


def paginated_response(
    items: list[Any],
    *,
    total: int,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    """Combine paginated items and pagination metadata."""
    metadata = get_pagination_metadata(total, page, page_size)

    return {
        "items": items,
        **metadata,
    }