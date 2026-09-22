"""Engine / session factories and a dev helper to create tables."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ..config import Config
from .base import Base


def make_engine(config: Config) -> Engine:
    kwargs: dict[str, Any] = {"echo": config.echo_sql, "future": True}
    if ":memory:" in config.sqlite_url:
        # In-memory SQLite is per-connection; share one connection across threads
        # (e.g. FastAPI's threadpool) so tables created at startup are visible.
        kwargs["poolclass"] = StaticPool
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(config.sqlite_url, **kwargs)


def make_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def init_db(engine: Engine) -> None:
    """Create all tables directly (tests / dev). Production uses Alembic."""
    Base.metadata.create_all(engine)
