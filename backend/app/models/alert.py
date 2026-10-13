from __future__ import annotations

from datetime import datetime

try:
    from sqlalchemy import DateTime, String, Text
    from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

    class Base(DeclarativeBase):
        pass

except ImportError:  # pragma: no cover - fallback for lightweight import checks.
    class Base:
        pass

    class Mapped:
        pass

    def mapped_column(*args, **kwargs):
        return None

    class DateTime:
        pass

    class String:
        def __init__(self, *args, **kwargs):
            pass

    class Text:
        def __init__(self, *args, **kwargs):
            pass


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="moderate")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="new")
    disease_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    region_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    acknowledged_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
