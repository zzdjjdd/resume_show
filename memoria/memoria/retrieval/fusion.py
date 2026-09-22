"""Reciprocal Rank Fusion for combining multi-layer ranked lists."""

from __future__ import annotations


def rrf(rank_lists: list[list[str]], k: int = 60) -> dict[str, float]:
    """Fuse several ranked id-lists into id -> score.

    Each list is ordered best-first. ``score = sum(1 / (k + rank))`` across the
    lists the id appears in. Robust to differing score scales between layers.
    """
    scores: dict[str, float] = {}
    for ranked in rank_lists:
        for rank, record_id in enumerate(ranked, start=1):
            scores[record_id] = scores.get(record_id, 0.0) + 1.0 / (k + rank)
    return scores
