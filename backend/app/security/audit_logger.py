from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog

# ---------------------------------------
# Logging Configuration
# ---------------------------------------

logger = logging.getLogger("health_surveillance.audit")

# ---------------------------------------
# Sensitive Data Protection
# ---------------------------------------

SENSITIVE_KEYS = {
    "password",
    "hashed_password",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "secret",
    "api_key",
    "phone",
    "email",
    "address",
    "date_of_birth",
    "symptoms",
    "medical_history",
    "patient_name",
    "national_id",
}


def sanitize_details(details: dict[str, Any] | None) -> dict[str, Any]:
    """
    Remove sensitive fields before storing audit metadata.

    Keep details limited to small, non-sensitive operational metadata.
    Do not pass complete request bodies or health records.
    """
    if not details:
        return {}

    sanitized: dict[str, Any] = {}

    for key, value in details.items():
        normalized_key = str(key).lower().replace("-", "_")

        if normalized_key in SENSITIVE_KEYS:
            sanitized[key] = "[REDACTED]"
            continue

        if isinstance(value, dict):
            sanitized[key] = sanitize_details(value)
        elif isinstance(value, list):
            sanitized[key] = f"[OMITTED: {len(value)} ITEMS]" if value else []
        elif isinstance(value, (str, int, float, bool)) or value is None:
            if isinstance(value, str):
                sanitized[key] = value[:200]
            else:
                sanitized[key] = value
        else:
            sanitized[key] = "[OMITTED]"

    return sanitized


# ---------------------------------------
# Audit Event Writer
# ---------------------------------------


def write_audit_log(
    db: Session,
    *,
    action: str,
    outcome: str,
    actor_user_id: int | None = None,
    resource_type: str | None = None,
    resource_id: str | int | None = None,
    details: dict[str, Any] | None = None,
) -> bool:
    """
    Persist a security audit event.

    Returns True when the database transaction is committed.
    Returns False if the event could not be persisted.

    The caller owns the supplied SQLAlchemy session. On failure, this
    function rolls back the session, so callers should not reuse a
    failed transaction without handling the failure.
    """
    try:
        if not action or len(action) > 100:
            raise ValueError("action must contain 1-100 characters.")

        if not outcome or len(outcome) > 30:
            raise ValueError("outcome must contain 1-30 characters.")

        if resource_type is not None and len(resource_type) > 100:
            raise ValueError("resource_type must not exceed 100 characters.")

        resource_id_text = (
            str(resource_id)[:100] if resource_id is not None else None
        )

        audit_entry = AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id_text,
            outcome=outcome,
            details=sanitize_details(details),
        )

        db.add(audit_entry)
        db.commit()

        logger.info(
            "Audit event persisted: action=%s outcome=%s resource_type=%s",
            action,
            outcome,
            resource_type,
        )

        return True
    except Exception:
        db.rollback()

        logger.error(
            "Failed to persist audit event: action=%s outcome=%s",
            action,
            outcome,
        )

        return False


# ---------------------------------------
# Convenience Helpers
# ---------------------------------------


def log_success(
    db: Session,
    *,
    action: str,
    actor_user_id: int | None = None,
    resource_type: str | None = None,
    resource_id: str | int | None = None,
    details: dict[str, Any] | None = None,
) -> bool:
    """Record a successful action."""
    return write_audit_log(
        db,
        action=action,
        outcome="success",
        actor_user_id=actor_user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
    )


def log_failure(
    db: Session,
    *,
    action: str,
    actor_user_id: int | None = None,
    resource_type: str | None = None,
    resource_id: str | int | None = None,
    details: dict[str, Any] | None = None,
) -> bool:
    """Record a failed action."""
    return write_audit_log(
        db,
        action=action,
        outcome="failure",
        actor_user_id=actor_user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
    )

