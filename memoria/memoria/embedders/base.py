"""Embedder contract. Every provider implements this interface."""

from __future__ import annotations

from abc import ABC, abstractmethod


class Embedder(ABC):
    """Turns text into a fixed-size vector.

    Implementations must be safe to construct without heavy dependencies or
    network access; expensive setup (loading a model, opening a client) should
    be deferred to first use via a lazy ``_load()``.
    """

    @property
    @abstractmethod
    def dim(self) -> int:
        """Dimensionality of produced vectors."""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Embed a single string."""

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed many strings. Default loops over :meth:`embed`."""
        return [self.embed(text) for text in texts]
