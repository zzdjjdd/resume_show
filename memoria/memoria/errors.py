"""Typed exceptions for Memoria."""

from __future__ import annotations


class MemoriaError(Exception):
    """Base class for all Memoria errors."""


class ConfigError(MemoriaError):
    """Raised for invalid or missing configuration."""


class EmbedderError(MemoriaError):
    """Raised when an embedding provider fails or is unavailable."""


class LLMError(MemoriaError):
    """Raised when an LLM provider fails or is unavailable."""


class VectorStoreError(MemoriaError):
    """Raised when a vector store backend fails or is unavailable."""


class NotFoundError(MemoriaError):
    """Raised when a requested memory record does not exist."""
