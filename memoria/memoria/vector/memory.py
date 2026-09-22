"""Dependency-free in-memory vector store.

The offline default and the backend used across the test suite. Pure-Python
cosine similarity; no numpy, no network, no persistence.
"""

from __future__ import annotations

import math
from typing import Any

from .base import VectorHit, VectorStore


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise ValueError("vectors must have equal length")
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _matches(metadata: dict[str, Any], where: dict[str, Any]) -> bool:
    return all(metadata.get(key) == value for key, value in where.items())


class InMemoryVectorStore(VectorStore):
    def __init__(self, **_: Any) -> None:
        self._items: dict[str, tuple[list[float], dict[str, Any]]] = {}

    def upsert(self, id: str, vector: list[float], metadata: dict[str, Any] | None = None) -> None:
        self._items[id] = (list(vector), dict(metadata or {}))

    def query(
        self,
        vector: list[float],
        top_k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[VectorHit]:
        hits: list[VectorHit] = []
        for id, (vec, meta) in self._items.items():
            if where and not _matches(meta, where):
                continue
            hits.append(VectorHit(id=id, score=cosine_similarity(vector, vec), metadata=meta))
        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[: max(0, top_k)]

    def delete(self, ids: list[str]) -> None:
        for id in ids:
            self._items.pop(id, None)

    def count(self) -> int:
        return len(self._items)
