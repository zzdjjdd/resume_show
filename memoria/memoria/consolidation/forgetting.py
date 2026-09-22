"""Forgetting: evict memories whose strength has decayed below a threshold.

Strength = importance x recency_decay(age) x (1 + log(1 + access_count)); the
recency time constant differs per layer (episodic fades fast, semantic slowly).
Eviction removes both the structured row and its vector. Procedural memory is
deliberately NOT decayed here — it is governed by reinforcement (success/failure).
"""

from __future__ import annotations

from ..stores.episodic import EpisodicStore
from ..stores.semantic import SemanticStore


class Forgetting:
    def __init__(self, episodic: EpisodicStore, semantic: SemanticStore) -> None:
        self._episodic = episodic
        self._semantic = semantic

    def forget(self, threshold: float = 0.05, max_keep: int | None = None) -> int:
        """Evict weak episodic + semantic memories. Returns number removed."""
        removed = self._episodic.forget(threshold=threshold, max_keep=max_keep)
        removed += self._semantic.forget(threshold=threshold, max_keep=max_keep)
        return len(removed)
