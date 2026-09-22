"""Cross-layer hybrid retrieval: per-layer recall -> RRF -> strength re-rank."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ..errors import ConfigError
from ..stores.base import MemoryRecord
from .fusion import rrf
from .scoring import TAU, strength


class Retriever:
    def __init__(self, stores: dict[str, Any]) -> None:
        self._stores = stores

    @property
    def layers(self) -> list[str]:
        return list(self._stores)

    def recall(
        self,
        query: str,
        layers: list[str] | None = None,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[MemoryRecord]:
        selected = layers or self.layers
        ranked_lists: list[list[str]] = []
        by_id: dict[str, MemoryRecord] = {}
        for layer in selected:
            store = self._stores.get(layer)
            if store is None:
                raise ConfigError(f"Unknown layer '{layer}'. Known: {self.layers}")
            records = store.search(query, top_k=max(top_k * 3, top_k), filters=filters)
            ranked_lists.append([r.id for r in records])
            for record in records:
                by_id[record.id] = record

        fused = rrf(ranked_lists)
        now = datetime.now(UTC)
        for record_id, record in by_id.items():
            tau = TAU.get(record.layer, TAU["semantic"])
            record.score = fused.get(record_id, 0.0) * strength(
                record.importance, record.created_at, record.access_count, tau, now
            )
        ordered = sorted(by_id.values(), key=lambda r: r.score, reverse=True)
        return ordered[:top_k]
