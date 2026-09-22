"""Semantic memory store: distilled stable facts / preferences.

``upsert`` dedupes on (namespace, subject, fact): re-asserting a fact merges
confidence (max) and unions the source-episode lineage instead of duplicating.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import sessionmaker

from ..db.base import utcnow
from ..db.models import SemanticMemory
from ..embedders.base import Embedder
from ..retrieval.scoring import TAU, strength
from ..vector.base import VectorStore
from .base import MemoryRecord

_SCALAR = (str, int, float, bool)


class SemanticStore:
    layer = "semantic"

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

    def _embed_text(self, subject: str, fact: str) -> list[float]:
        return self._embedder.embed(f"{subject}: {fact}")

    def upsert(
        self,
        subject: str,
        fact: str,
        confidence: float = 0.5,
        source_episode_ids: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        with self._sessionmaker() as session:
            existing = (
                session.query(SemanticMemory)
                .filter_by(namespace=self._namespace, subject=subject, fact=fact)
                .first()
            )
            if existing is not None:
                existing.confidence = max(existing.confidence, confidence)
                if source_episode_ids:
                    prior = set(existing.source_episode_ids or [])
                    prior.update(source_episode_ids)
                    existing.source_episode_ids = sorted(prior)
                existing.updated_at = utcnow()
                record_id = existing.id
            else:
                record_id = str(uuid.uuid4())
                session.add(
                    SemanticMemory(
                        id=record_id,
                        namespace=self._namespace,
                        subject=subject,
                        fact=fact,
                        confidence=confidence,
                        source_episode_ids=sorted(set(source_episode_ids or [])) or None,
                    )
                )
            session.commit()

        vector_meta: dict[str, Any] = {
            "namespace": self._namespace,
            "importance": float(confidence),
        }
        if metadata:
            vector_meta.update({k: v for k, v in metadata.items() if isinstance(v, _SCALAR)})
        self._vector.upsert(record_id, self._embed_text(subject, fact), vector_meta)
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
            rows = session.query(SemanticMemory).filter(SemanticMemory.id.in_(ordered_ids)).all()
            by_id = {row.id: row for row in rows}
            for record_id in ordered_ids:
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
                        content=f"{row.subject}: {row.fact}",
                        importance=row.confidence,
                        score=scores.get(record_id, 0.0),
                        access_count=row.access_count,
                        created_at=row.created_at,
                        metadata={"subject": row.subject},
                    )
                )
            session.commit()
        return records

    def count(self, namespace: str | None = None) -> int:
        with self._sessionmaker() as session:
            return (
                session.query(SemanticMemory)
                .filter_by(namespace=namespace or self._namespace)
                .count()
            )

    def get(self, record_id: str) -> SemanticMemory | None:
        with self._sessionmaker() as session:
            return session.get(SemanticMemory, record_id)

    def list_all(self) -> list[SemanticMemory]:
        """All rows in this namespace (used by snapshot / API)."""
        with self._sessionmaker() as session:
            return session.query(SemanticMemory).filter_by(namespace=self._namespace).all()

    def delete(self, record_id: str) -> bool:
        with self._sessionmaker() as session:
            row = session.get(SemanticMemory, record_id)
            if row is None:
                return False
            session.delete(row)
            session.commit()
        self._vector.delete([record_id])
        return True

    def forget(
        self,
        threshold: float = 0.05,
        max_keep: int | None = None,
    ) -> list[str]:
        """Evict low-strength facts (importance here = confidence)."""
        tau = TAU[self.layer]
        now = utcnow()
        with self._sessionmaker() as session:
            rows = session.query(SemanticMemory).filter_by(namespace=self._namespace).all()
            scored = [
                (row, strength(row.confidence, row.created_at, row.access_count or 0, tau, now))
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
        subject: str | None = None,
        fact_contains: str | None = None,
    ) -> list[str]:
        """Delete facts matching the conditions; no conditions = wipe namespace."""
        with self._sessionmaker() as session:
            query = session.query(SemanticMemory).filter_by(namespace=self._namespace)
            if subject is not None:
                query = query.filter_by(subject=subject)
            if fact_contains is not None:
                query = query.filter(SemanticMemory.fact.like(f"%{fact_contains}%"))
            rows = query.all()
            removed = [row.id for row in rows]
            for row in rows:
                session.delete(row)
            session.commit()
        if removed:
            self._vector.delete(removed)
        return removed
