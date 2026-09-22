"""OpenAI (and API-compatible) embedder — lazy import.

Works with any OpenAI-compatible endpoint, e.g. Alibaba DashScope
(Qwen ``text-embedding-v3``) by setting ``base_url``. Credentials come from the
constructor or environment and are never persisted:
    api_key  <- arg > EMBEDDER_API_KEY > OPENAI_API_KEY
    base_url <- arg > EMBEDDER_BASE_URL > OPENAI_BASE_URL
``dimensions`` is passed through for models that support flexible output size
(Qwen text-embedding-v3, OpenAI text-embedding-3-*).
"""

from __future__ import annotations

import os
from typing import Any

from ..errors import EmbedderError
from .base import Embedder


class OpenAIEmbedder(Embedder):
    def __init__(
        self,
        model: str | None = None,
        dim: int = 1536,
        api_key: str | None = None,
        base_url: str | None = None,
        dimensions: int | None = None,
        **_: Any,
    ) -> None:
        self._model = model or "text-embedding-3-small"
        self._dim = dimensions or dim
        self._dimensions = dimensions
        self._api_key = (
            api_key or os.environ.get("EMBEDDER_API_KEY") or os.environ.get("OPENAI_API_KEY")
        )
        self._base_url = (
            base_url or os.environ.get("EMBEDDER_BASE_URL") or os.environ.get("OPENAI_BASE_URL")
        )
        self._client: Any = None

    @property
    def dim(self) -> int:
        return self._dim

    def _load(self) -> Any:
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:  # pragma: no cover - depends on env
                raise EmbedderError(
                    "openai is not installed. Run: pip install 'memoria[openai]'"
                ) from exc
            if not self._api_key:
                raise EmbedderError(
                    "Embedding API key missing (set EMBEDDER_API_KEY or OPENAI_API_KEY)."
                )
            kwargs: dict[str, Any] = {"api_key": self._api_key}
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = OpenAI(**kwargs)
        return self._client

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        client = self._load()
        params: dict[str, Any] = {"model": self._model, "input": list(texts)}
        if self._dimensions is not None:
            params["dimensions"] = self._dimensions
        resp = client.embeddings.create(**params)
        return [list(map(float, item.embedding)) for item in resp.data]
