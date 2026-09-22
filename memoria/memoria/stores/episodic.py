"""Episodic memory store: what happened, when, where.

Writes go to both the structured table (SQLite) and the vector store under the
same id. Retrieval does a vector similarity search scoped to the namespace,
hydrates ORM rows in rank order, and records the access (so frequently recalled
memories grow stronger — see forgetting).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import sessionmaker

from ..db.base import utcnow
from ..db.models import EpisodicMemory
from ..embedders.base import Embedder
from ..retrieval.scoring import TAU, strength
from ..vector.base import VectorStore
from .base import MemoryRecord

_SCALAR = (str, int, float, bool)


class EpisodicStore:
    layer = "episodic"

    def __init__(
        self,
        sessionmaker: sessionmaker[Any],
        vector_store: VectorStore,
        embedder: Embedder,
        namespace: str,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._vector = vector_store
        self._embedder = embedder
        self._namespace = namespace

    def add(
        self,
        content: str,
        importance: float = 0.5,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        record_id = str(uuid.uuid4())
        vector = self._embedder.embed(content)

        vector_meta: dict[str, Any] = {
            "namespace": self._namespace,
            "importance": float(importance),
        }
        if metadata:
            vector_meta.update({k: v for k, v in metadata.items() if isinstance(v, _SCALAR)})
        self._vector.upsert(record_id, vector, vector_meta)

        with self._sessionmaker() as session:
            session.add(
                EpisodicMemory(
                    id=record_id,
                    namespace=self._namespace,
                    session_id=session_id,
                    content=content,
                    importance=importance,
                    metadata_=metadata,
                )
            )
            session.commit()
        return record_id

    def search(
        self,
        query: str,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[MemoryRecord]:
        vector = self._embedder.embed(query)
        where: dict[str, Any] = {"namespace": self._namespace}
        if filters:
            where.update(filters)
        hits = self._vector.query(vector, top_k=top_k, where=where)
        if not hits:
            return []

        ordered_ids = [hit.id for hit in hits]
        scores = {hit.id: hit.score for hit in hits}

        records: list[MemoryRecord] = []
        with self._sessionmaker() as session:
            rows = session.query(EpisodicMemory).filter(EpisodicMemory.id.in_(ordered_ids)).all()
            by_id = {row.id: row for row in rows}
            for record_id in ordered_ids:  # preserve vector ranking
                row = by_id.get(record_id)
                if row is None:
                    continue
                row.access_count = (row.access_count or 0) + 1
                row.last_accessed_at = utcnow()
                records.append(
                    MemoryRecord(
                        id=row.id,
                        layer=self.layer,
                        namespace=row.namespace,
                        content=row.content,
                        importance=row.importance,
                        score=scores.get(record_id, 0.0),
                        access_count=row.access_count,
                        created_at=row.created_at,
                        metadata=row.metadata_ or {},
                    )
                )
            session.commit()
        return records

    def count(self, namespace: str | None = None) -> int:
        with self._sessionmaker() as session:
            return (
                session.query(EpisodicMemory)
                .filter_by(namespace=namespace or self._namespace)
                .count()
            )

    def get(self, record_id: str) -> EpisodicMemory | None:
        with self._sessionmaker() as session:
            return session.get(EpisodicMemory, record_id)

    def list_all(self) -> list[EpisodicMemory]:
        """All rows in this namespace (used by consolidation)."""
        with self._sessionmaker() as session:
            return session.query(EpisodicMemory).filter_by(namespace=self._namespace).all()

    def delete(self, record_id: str) -> bool:
        with self._sessionmaker() as session:
            row = session.get(EpisodicMemory, record_id)
            if row is None:
                return False
            session.delete(row)
            session.commit()
        self._vector.delete([record_id])
        return True

    def forget(self, threshold: float = 0.05, max_keep: int | None = None) -> list[str]:
        """Evict low-strength episodes: strength < threshold, or weakest past max_keep."""
        tau = TAU[self.layer]
        now = utcnow()
        with self._sessionmaker() as session:
            rows = session.query(EpisodicMemory).filter_by(namespace=self._namespace).all()
            scored = [
                (row, strength(row.importance, row.created_at, row.access_count or 0, tau, now))
                for row in rows
            ]
            weak_ids = {row.id for row, sc in scored if sc < threshold}
            if max_keep is not None and len(scored) > max_keep:
                weakest = sorted(scored, key=lambda item: item[1])
                excess = len(scored) - max_keep
                weak_ids.update(row.id for row, _sc in weakest[:excess])
            to_delete = [row for row in rows if row.id in weak_ids]
            removed = [row.id for row in to_delete]
            for row in to_delete:
                session.delete(row)
            session.commit()
        if removed:
            self._vector.delete(removed)
        return removed

    def delete_where(
        self,
        content_contains: str | None = None,
        metadata_match: dict[str, Any] | None = None,
    ) -> list[str]:
        """Delete episodes matching the conditions; no conditions = wipe namespace."""
        with self._sessionmaker() as session:
            query = session.query(EpisodicMemory).filter_by(namespace=self._namespace)
            if content_contains is not None:
                query = query.filter(EpisodicMemory.content.like(f"%{content_contains}%"))
            rows = query.all()
            if metadata_match:
                rows = [
                    row
                    for row in rows
                    if all((row.metadata_ or {}).get(k) == v for k, v in metadata_match.items())
                ]
            removed = [row.id for row in rows]
            for row in rows:
                session.delete(row)
            session.commit()
        if removed:
            self._vector.delete(removed)
        return removed
