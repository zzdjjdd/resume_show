"""Create an :class:`Embedder` by name.

Backends are imported lazily so constructing a ``Memory`` with the default
``"fake"`` embedder never pulls in sentence-transformers / openai.
"""

from __future__ import annotations

import importlib
from typing import Any

from ..errors import ConfigError
from .base import Embedder

# name -> "module.Class"
_REGISTRY: dict[str, str] = {
    "fake": "memoria.embedders.fake.DeterministicFakeEmbedder",
    "local": "memoria.embedders.local.SentenceTransformerEmbedder",
    "sentence-transformers": "memoria.embedders.local.SentenceTransformerEmbedder",
    "openai": "memoria.embedders.openai.OpenAIEmbedder",
}


def available_embedders() -> list[str]:
    return sorted(set(_REGISTRY))


def get_embedder(name: str, **kwargs: Any) -> Embedder:
    key = name.strip().lower()
    if key not in _REGISTRY:
        raise ConfigError(
            f"Unknown embedder '{name}'. Available: {available_embedders()}"
        )
    module_path, _, class_name = _REGISTRY[key].rpartition(".")
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    embedder: Embedder = cls(**kwargs)
    return embedder
