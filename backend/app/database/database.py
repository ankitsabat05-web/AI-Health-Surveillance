from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Shared declarative base for database models."""


DATABASE_URL = "sqlite:///./health_surveillance.db"
engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Iterator[Session]:
    """Yield a database session for route handlers."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
