"""Create a :class:`VectorStore` by name (backends imported lazily)."""

from __future__ import annotations

import importlib
from typing import Any

from ..errors import ConfigError
from .base import VectorStore

_REGISTRY: dict[str, str] = {
    "memory": "memoria.vector.memory.InMemoryVectorStore",
    "in-memory": "memoria.vector.memory.InMemoryVectorStore",
    "chroma": "memoria.vector.chroma.ChromaVectorStore",
}


def available_vector_stores() -> list[str]:
    return sorted(set(_REGISTRY))


def get_vector_store(name: str, **kwargs: Any) -> VectorStore:
    key = name.strip().lower()
    if key not in _REGISTRY:
        raise ConfigError(
            f"Unknown vector store '{name}'. Available: {available_vector_stores()}"
        )
    module_path, _, class_name = _REGISTRY[key].rpartition(".")
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    store: VectorStore = cls(**kwargs)
    return store
