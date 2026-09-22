"""Deterministic, dependency-free embedder.

Used as the offline default and throughout the test suite. The same text always
produces the same (normalized) vector, so retrieval tests are reproducible
without a real model or network.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any

from .base import Embedder


class DeterministicFakeEmbedder(Embedder):
    def __init__(self, dim: int = 384, **_: Any) -> None:
        if dim <= 0:
            raise ValueError("dim must be > 0")
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self._dim
        seed = text.encode("utf-8")
        idx = 0
        counter = 0
        while idx < self._dim:
            digest = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
            for byte in digest:
                if idx >= self._dim:
                    break
                vec[idx] = (byte / 255.0) * 2.0 - 1.0
                idx += 1
            counter += 1
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]
