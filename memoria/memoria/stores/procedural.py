"""Procedural memory store: how to do things (skills / workflows).

Retrieval matches against ``trigger`` (+ step) text. Successful use reinforces
a procedure (success_count up), failure down-weights it; importance grows with
demonstrated success so well-proven routines surface first.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import sessionmaker

from ..db.base import utcnow
from ..db.models import ProceduralMemory
from ..embedders.base import Embedder
from ..vector.base import VectorStore
from .base import MemoryRecord

_SCALAR = (str, int, float, bool)


class ProceduralStore:
    layer = "procedural"

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

    @staticmethod
    def _importance(row: ProceduralMemory) -> float:
        return min(0.95, 0.5 + 0.05 * (row.success_count or 0))

    def add(self, trigger: str, steps: list[str], metadata: dict[str, Any] | None = None) -> str:
        record_id = str(uuid.uuid4())
        text = trigger + " " + " ".join(steps)
        vector_meta: dict[str, Any] = {"namespace": self._namespace}
        if metadata:
            vector_meta.update({k: v for k, v in metadata.items() if isinstance(v, _SCALAR)})
        self._vector.upsert(record_id, self._embedder.embed(text), vector_meta)
        with self._sessionmaker() as session:
            session.add(
                ProceduralMemory(
                    id=record_id,
                    namespace=self._namespace,
                    trigger=trigger,
                    steps=list(steps),
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
            rows = (
                session.query(ProceduralMemory)
                .filter(ProceduralMemory.id.in_(ordered_ids))
                .all()
            )
            by_id = {row.id: row for row in rows}
            for record_id in ordered_ids:
                row = by_id.get(record_id)
                if row is None:
                    continue
                row.last_used_at = utcnow()
                records.append(
                    MemoryRecord(
                        id=row.id,
                        layer=self.layer,
                        namespace=row.namespace,
                        content=f"{row.trigger}: " + " → ".join(row.steps or []),
                        importance=self._importance(row),
                        score=scores.get(record_id, 0.0),
                        access_count=row.success_count or 0,
                        created_at=row.created_at,
                        metadata={"steps": row.steps or []},
                    )
                )
            session.commit()
        return records

    def reinforce(self, record_id: str, success: bool) -> bool:
        with self._sessionmaker() as session:
            row = session.get(ProceduralMemory, record_id)
            if row is None:
                return False
            if success:
                row.success_count = (row.success_count or 0) + 1
            else:
                row.failure_count = (row.failure_count or 0) + 1
            row.last_used_at = utcnow()
            session.commit()
        return True

    def count(self, namespace: str | None = None) -> int:
        with self._sessionmaker() as session:
            return (
                session.query(ProceduralMemory)
                .filter_by(namespace=namespace or self._namespace)
                .count()
            )

    def get(self, record_id: str) -> ProceduralMemory | None:
        with self._sessionmaker() as session:
            return session.get(ProceduralMemory, record_id)

    def list_all(self) -> list[ProceduralMemory]:
        """All rows in this namespace (used by snapshot / API)."""
        with self._sessionmaker() as session:
            return session.query(ProceduralMemory).filter_by(namespace=self._namespace).all()

    def delete(self, record_id: str) -> bool:
        with self._sessionmaker() as session:
            row = session.get(ProceduralMemory, record_id)
            if row is None:
                return False
            session.delete(row)
            session.commit()
        self._vector.delete([record_id])
        return True

    def delete_where(self, trigger_contains: str | None = None) -> list[str]:
        """Delete procedures matching the condition; no condition = wipe namespace."""
        with self._sessionmaker() as session:
            query = session.query(ProceduralMemory).filter_by(namespace=self._namespace)
            if trigger_contains is not None:
                query = query.filter(ProceduralMemory.trigger.like(f"%{trigger_contains}%"))
            rows = query.all()
            removed = [row.id for row in rows]
            for row in rows:
                session.delete(row)
            session.commit()
        if removed:
            self._vector.delete(removed)
        return removed
