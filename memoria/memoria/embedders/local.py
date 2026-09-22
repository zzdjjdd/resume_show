"""sentence-transformers backed embedder (lazy import).

Construction is cheap and offline; the model is only loaded on first
``embed`` call. Swap the model via the ``model`` argument / ``Config.embedder_model``.
"""

from __future__ import annotations

from typing import Any

from ..errors import EmbedderError
from .base import Embedder


class SentenceTransformerEmbedder(Embedder):
    def __init__(
        self,
        model: str | None = None,
        dim: int = 384,
        device: str | None = None,
        **_: Any,
    ) -> None:
        self._model_name = model or "all-MiniLM-L6-v2"
        self._dim = dim
        self._device = device
        self._model: Any = None

    @property
    def dim(self) -> int:
        if self._model is not None:
            return int(self._model.get_sentence_embedding_dimension())
        return self._dim

    def _load(self) -> Any:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:  # pragma: no cover - depends on env
                raise EmbedderError(
                    "sentence-transformers is not installed. "
                    "Run: pip install 'memoria[local]'"
                ) from exc
            kwargs: dict[str, Any] = {}
            if self._device:
                kwargs["device"] = self._device
            self._model = SentenceTransformer(self._model_name, **kwargs)
        return self._model

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        model = self._load()
        arr = model.encode(list(texts), normalize_embeddings=True)
        return [list(map(float, row)) for row in arr]
