"""Memoria — embedded short-term + long-term memory for agent applications.

Four-layer cognitive model (working / episodic / semantic / procedural) over a
hybrid store (vector + structured). Start with :class:`Memory`.
"""

from __future__ import annotations

from .config import Config
from .errors import (
    ConfigError,
    EmbedderError,
    MemoriaError,
    NotFoundError,
    VectorStoreError,
)
from .manager import Memory

__version__ = "0.0.1"

__all__ = [
    "Config",
    "ConfigError",
    "EmbedderError",
    "Memory",
    "MemoriaError",
    "NotFoundError",
    "VectorStoreError",
    "__version__",
]
