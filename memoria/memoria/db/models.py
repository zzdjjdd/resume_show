"""ORM models for the long-term memory layers.

Working memory is intentionally NOT here: it is an in-process, ephemeral buffer
(see ``memoria.stores.working`` in M1). Each long-term record is mirrored in the
vector store (Chroma) under the same ``id``.

Note: the JSON column on episodic memory is named ``metadata`` in the database
but exposed as the ``metadata_`` attribute, because ``metadata`` is reserved by
SQLAlchemy's declarative machinery.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, utcnow


class EpisodicMemory(Base):
    """What happened, when, where. Decays over time."""

    __tablename__ = "episodic_memory"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    namespace: Mapped[str] = mapped_column(String(128), index=True)
    session_id: Mapped[str | None] = mapped_column(String(128), index=True)
    content: Mapped[str] = mapped_column(Text)
    importance: Mapped[float] = mapped_column(Float, default=0.5)
    access_count: Mapped[int] = mapped_column(Integer, default=0)
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<EpisodicMemory id={self.id!r} namespace={self.namespace!r}>"


class SemanticMemory(Base):
    """Distilled stable facts / preferences. Highly durable."""

    __tablename__ = "semantic_memory"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    namespace: Mapped[str] = mapped_column(String(128), index=True)
    subject: Mapped[str] = mapped_column(String(256), index=True)
    fact: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    source_episode_ids: Mapped[list[str] | None] = mapped_column(JSON)
    access_count: Mapped[int] = mapped_column(Integer, default=0)
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<SemanticMemory id={self.id!r} subject={self.subject!r}>"


class ProceduralMemory(Base):
    """How to do things. Reinforced by successful use, down-weighted by failure."""

    __tablename__ = "procedural_memory"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    namespace: Mapped[str] = mapped_column(String(128), index=True)
    # Column is named trigger_condition in SQL ("trigger" is a reserved word).
    trigger: Mapped[str] = mapped_column("trigger_condition", Text)
    steps: Mapped[list[str] | None] = mapped_column(JSON)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<ProceduralMemory id={self.id!r} trigger={self.trigger!r}>"
