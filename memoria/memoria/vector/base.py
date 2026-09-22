"""Vector store contract plus a lightweight hit record."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class VectorHit:
    """A single result from a vector similarity query."""

    id: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorStore(ABC):
    """Stores vectors keyed by id and answers top-k similarity queries.

    Implementations must be safe to construct offline; heavy setup (opening a
    client / persistent collection) should be deferred to first use.
    """

    @abstractmethod
    def upsert(self, id: str, vector: list[float], metadata: dict[str, Any] | None = None) -> None:
        """Insert or replace the vector for ``id``."""

    @abstractmethod
    def query(
        self,
        vector: list[float],
        top_k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[VectorHit]:
        """Return up to ``top_k`` most similar ids, optionally metadata-filtered."""

    @abstractmethod
    def delete(self, ids: list[str]) -> None:
        """Delete the given ids (missing ids are ignored)."""

    def count(self) -> int:  # pragma: no cover - optional
        raise NotImplementedError
