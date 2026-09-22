"""Create an :class:`LLM` by name (backends imported lazily)."""

from __future__ import annotations

import importlib
from typing import Any

from ..errors import ConfigError
from .base import LLM

_REGISTRY: dict[str, str] = {
    "fake": "memoria.llms.fake.FakeLLM",
    "openai": "memoria.llms.openai_compat.OpenAICompatLLM",
    "openai-compat": "memoria.llms.openai_compat.OpenAICompatLLM",
    "deepseek": "memoria.llms.openai_compat.OpenAICompatLLM",
}


def available_llms() -> list[str]:
    return sorted(set(_REGISTRY))


def get_llm(name: str, **kwargs: Any) -> LLM:
    key = name.strip().lower()
    if key not in _REGISTRY:
        raise ConfigError(f"Unknown LLM '{name}'. Available: {available_llms()}")
    module_path, _, class_name = _REGISTRY[key].rpartition(".")
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    llm: LLM = cls(**kwargs)
    return llm
