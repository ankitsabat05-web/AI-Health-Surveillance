from __future__ import annotations

import logging

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.disease import Disease
from app.schemas.disease_schema import DiseaseCreate, DiseaseUpdate

logger = logging.getLogger("health_surveillance.disease_service")


# ---------------------------------------
# Helpers
# ---------------------------------------

def normalize_disease_name(name: str) -> str:
    """Normalize whitespace and casing for duplicate checks."""
    return " ".join(name.strip().split())


def get_disease_or_404(db: Session, disease_id: int) -> Disease:
    """Retrieve a disease or return HTTP 404."""
    disease = db.get(Disease, disease_id)

    if disease is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Disease not found.",
        )

    return disease


def ensure_unique_disease_name(
    db: Session,
    name: str,
    *,
    exclude_id: int | None = None,
) -> None:
    """Prevent duplicate disease names, ignoring letter casing."""
    statement = select(Disease.id).where(func.lower(Disease.name) == func.lower(name))

    if exclude_id is not None:
        statement = statement.where(Disease.id != exclude_id)

    if db.scalar(statement) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A disease with this name already exists.",
        )


# ---------------------------------------
# Create Disease
# ---------------------------------------

def create_disease(
    db: Session,
    disease_data: DiseaseCreate,
) -> Disease:
    """Add a disease to the monitoring catalogue."""
    name = normalize_disease_name(disease_data.name)
    ensure_unique_disease_name(db, name)

    disease = Disease(
        name=name,
        description=disease_data.description,
        category=disease_data.category,
        is_monitored=True,
    )

    try:
        db.add(disease)
        db.commit()
        db.refresh(disease)
        return disease
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Unable to create disease because the record conflicts with existing data.",
        ) from None
    except SQLAlchemyError:
        db.rollback()
        logger.error("Database error while creating disease.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Disease service is temporarily unavailable.",
        ) from None


# ---------------------------------------
# Get Disease
# ---------------------------------------

def get_disease(
    db: Session,
    disease_id: int,
) -> Disease:
    """Retrieve a disease by its ID."""
    return get_disease_or_404(db, disease_id)


# ---------------------------------------
# List Diseases
# ---------------------------------------

def list_diseases(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    monitored_only: bool = False,
    search: str | None = None,
) -> dict:
    """Retrieve diseases with bounded pagination and optional search."""
    if page < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Page must be at least 1.",
        )

    if not 1 <= page_size <= 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Page size must be between 1 and 100.",
        )

    statement = select(Disease)
    count_statement = select(func.count()).select_from(Disease)

    if monitored_only:
        statement = statement.where(Disease.is_monitored.is_(True))
        count_statement = count_statement.where(Disease.is_monitored.is_(True))

    if search:
        term = search.strip()

        if term:
            escaped_term = (
                term.replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            condition = Disease.name.ilike(f"%{escaped_term}%", escape="\\")

            statement = statement.where(condition)
            count_statement = count_statement.where(condition)

    total = db.scalar(count_statement) or 0

    diseases = db.scalars(
        statement.order_by(Disease.name.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return {
        "items": list(diseases),
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }


# ---------------------------------------
# Update Disease
# ---------------------------------------

def update_disease(
    db: Session,
    disease_id: int,
    disease_data: DiseaseUpdate,
) -> Disease:
    """Update an existing disease record."""
    disease = get_disease_or_404(db, disease_id)

    changes = disease_data.model_dump(exclude_unset=True)

    if not changes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one field must be provided.",
        )

    if "name" in changes:
        if changes["name"] is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Disease name cannot be null.",
            )

        changes["name"] = normalize_disease_name(changes["name"])
        ensure_unique_disease_name(
            db,
            changes["name"],
            exclude_id=disease_id,
        )

    if "is_monitored" in changes and changes["is_monitored"] is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Monitoring status cannot be null.",
        )

    for field, value in changes.items():
        setattr(disease, field, value)

    try:
        db.commit()
        db.refresh(disease)
        return disease
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Unable to update disease because the record conflicts with existing data.",
        ) from None
    except SQLAlchemyError:
        db.rollback()
        logger.error("Database error while updating disease.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Disease service is temporarily unavailable.",
        ) from None


# ---------------------------------------
# Enable / Disable Monitoring
# ---------------------------------------

def set_disease_monitoring(
    db: Session,
    disease_id: int,
    *,
    enabled: bool,
) -> Disease:
    """Enable or disable monitoring for an existing disease."""
    disease = get_disease_or_404(db, disease_id)

    disease.is_monitored = enabled

    try:
        db.commit()
        db.refresh(disease)
        return disease
    except SQLAlchemyError:
        db.rollback()
        logger.error("Database error while changing disease monitoring.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Disease service is temporarily unavailable.",
        ) from None


# ---------------------------------------
# Delete Disease
# ---------------------------------------

def delete_disease(
    db: Session,
    disease_id: int,
) -> None:
    """Delete a disease only when the database permits it."""
    disease = get_disease_or_404(db, disease_id)

    try:
        db.delete(disease)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This disease is referenced by other records and cannot be deleted.",
        ) from None
    except SQLAlchemyError:
        db.rollback()
        logger.error("Database error while deleting disease.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Disease service is temporarily unavailable.",
        ) from None