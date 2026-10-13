import logging

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database.database import Base, SessionLocal, engine

# Import models so SQLAlchemy registers their tables.
from app.models import Disease, Location

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --------------------------------------------------
# INITIAL DISEASE CATALOGUE
# --------------------------------------------------

DISEASES = [
    {
        "name": "Dengue",
        "description": "Mosquito-borne viral infection.",
        "category": "Vector-borne",
        "is_monitored": True,
    },
    {
        "name": "Malaria",
        "description": "Mosquito-borne parasitic infection.",
        "category": "Vector-borne",
        "is_monitored": True,
    },
    {
        "name": "Influenza",
        "description": "Respiratory infection caused by influenza viruses.",
        "category": "Respiratory",
        "is_monitored": True,
    },
    {
        "name": "COVID-19",
        "description": "Respiratory illness caused by SARS-CoV-2.",
        "category": "Respiratory",
        "is_monitored": True,
    },
    {
        "name": "Typhoid",
        "description": "Bacterial infection caused by Salmonella Typhi.",
        "category": "Water- and food-associated",
        "is_monitored": True,
    },
]


# --------------------------------------------------
# DEMONSTRATION LOCATIONS
# --------------------------------------------------
# These are examples for local development, not official
# public-health boundaries or verified population records.

LOCATIONS = [
    {
        "region_code": "DEMO-MH-001",
        "region_name": "Demo Region A",
        "district": "Demo District A",
        "state": "Maharashtra",
        "country": "India",
        "population": None,
        "latitude": None,
        "longitude": None,
        "is_active": True,
    },
    {
        "region_code": "DEMO-MH-002",
        "region_name": "Demo Region B",
        "district": "Demo District B",
        "state": "Maharashtra",
        "country": "India",
        "population": None,
        "latitude": None,
        "longitude": None,
        "is_active": True,
    },
    {
        "region_code": "DEMO-MH-003",
        "region_name": "Demo Region C",
        "district": "Demo District C",
        "state": "Maharashtra",
        "country": "India",
        "population": None,
        "latitude": None,
        "longitude": None,
        "is_active": True,
    },
]


# --------------------------------------------------
# SEED HELPER
# --------------------------------------------------

def seed_diseases(db: Session) -> int:
    """Insert missing diseases without duplicating existing records."""
    added = 0

    for item in DISEASES:
        existing = db.scalar(
            select(Disease).where(Disease.name == item["name"])
        )

        if existing is not None:
            logger.info("Disease already exists: %s", item["name"])
            continue

        db.add(Disease(**item))
        added += 1

    return added


def seed_locations(db: Session) -> int:
    """Insert missing demonstration locations."""
    added = 0

    for item in LOCATIONS:
        existing = db.scalar(
            select(Location).where(
                Location.region_code == item["region_code"]
            )
        )

        if existing is not None:
            logger.info(
                "Location already exists: %s",
                item["region_code"],
            )
            continue

        db.add(Location(**item))
        added += 1

    return added


# --------------------------------------------------
# MAIN SEED FUNCTION
# --------------------------------------------------

def seed_database() -> None:
    """
    Initialize missing tables for local development and seed
    the disease catalogue and demonstration locations.

    Production schema changes should use Alembic migrations.
    """
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    try:
        diseases_added = seed_diseases(db)
        locations_added = seed_locations(db)

        db.commit()

        logger.info("Database seeding completed.")
        logger.info("New diseases: %s", diseases_added)
        logger.info("New locations: %s", locations_added)

    except SQLAlchemyError:
        db.rollback()
        logger.exception("Database seeding failed.")
        raise

    finally:
        db.close()


if __name__ == "__main__":
    seed_database()