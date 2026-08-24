"""SQLAlchemy declarative base and shared column helpers."""

from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    """Return an aware UTC timestamp for ORM defaults."""

    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Base for all persisted DigitalMe models."""


class TimestampMixin:
    """Created/updated timestamps shared by mutable records."""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
