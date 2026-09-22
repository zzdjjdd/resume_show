"""Shared store primitives.

Concrete per-layer stores land in M1/M2. This module defines the
layer-agnostic record returned by retrieval and the minimal store contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass
class MemoryRecord:
    """A single retrieved memory, regardless of its source layer."""

    id: str
    layer: str
    namespace: str
    content: str
    importance: float = 0.5
    score: float = 0.0
    access_count: int = 0
    created_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class Store(Protocol):
    """Minimal contract every layer store satisfies."""

    layer: str

    def count(self, namespace: str) -> int:
        """Number of records in a namespace."""
        ...
