"""Recall-quality evaluation harness.

Given ``(query, expected_content)`` cases, measures whether the expected memory
is recovered within the top-k. The reported hit-rate reflects the *retrieval
pipeline* (vector recall -> RRF -> strength re-rank). Semantic precision
additionally depends on the configured embedder — with the offline ``fake``
embedder, use exact-text queries.
"""

from __future__ import annotations

from typing import Any

from .manager import Memory


def evaluate_recall(
    mem: Memory,
    cases: list[tuple[str, str]],
    top_k: int = 3,
    layers: list[str] | None = None,
) -> dict[str, Any]:
    hits = 0
    misses: list[dict[str, Any]] = []
    for query, expected in cases:
        records = mem.recall(query, layers=layers, top_k=top_k)
        if any(expected in r.content for r in records):
            hits += 1
        else:
            misses.append(
                {"query": query, "expected": expected, "got": [r.content for r in records]}
            )
    total = len(cases)
    return {
        "total": total,
        "hits": hits,
        "hit_rate": (hits / total) if total else 0.0,
        "top_k": top_k,
        "misses": misses,
    }
