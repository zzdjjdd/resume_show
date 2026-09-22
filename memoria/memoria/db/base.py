"""SQLAlchemy declarative base and shared helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all ORM models."""


def utcnow() -> datetime:
    """Timezone-aware UTC now (used as a column default factory)."""
    return datetime.now(UTC)
