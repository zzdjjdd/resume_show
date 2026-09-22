"""Memory-strength scoring: importance x recency x frequency.

A single source of truth shared by retrieval (final re-ranking) and forgetting
(decay/eviction). ``tau`` controls how fast recency decays per layer — episodic
memories fade quickly, semantic/procedural knowledge fades slowly.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

DAY = 86_400.0

# Per-layer recency half-life-ish time constants (seconds).
TAU: dict[str, float] = {
    "episodic": 30 * DAY,
    "semantic": 365 * DAY,
    "procedural": 365 * DAY,
}


def _to_aware(dt: datetime) -> datetime:
    """SQLite returns naive datetimes; treat them as UTC."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def recency_decay(age_seconds: float, tau_seconds: float) -> float:
    if tau_seconds <= 0:
        return 1.0
    return math.exp(-max(0.0, age_seconds) / tau_seconds)


def strength(
    importance: float,
    created_at: datetime | None,
    access_count: int,
    tau_seconds: float,
    now: datetime | None = None,
) -> float:
    """importance x recency_decay(age) x (1 + log(1 + access_count))."""
    moment = now or datetime.now(UTC)
    if created_at is None:
        decay = 1.0
    else:
        age = (moment - _to_aware(created_at)).total_seconds()
        decay = recency_decay(age, tau_seconds)
    return importance * decay * (1.0 + math.log1p(max(0, access_count)))
