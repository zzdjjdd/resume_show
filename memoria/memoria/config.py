"""Configuration for a :class:`memoria.Memory` instance.

Keep this module dependency-free and dumb: it only holds settings. Providers
(embedder / LLM) and storage engines are resolved elsewhere from these values,
so swapping a model or a backend never requires changing business code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Config:
    """Runtime configuration.

    Attributes:
        sqlite_url: SQLAlchemy URL for the structured store.
        chroma_path: Persistent directory for the Chroma vector store.
        vector_store: Vector backend name — ``"memory"`` (offline default) or
            ``"chroma"`` (persistent, production).
        vector_collection: Collection name used by the vector backend.
        embedder: Embedder backend name — ``"fake"`` (offline default),
            ``"local"`` (sentence-transformers) or ``"openai"`` (also used for
            OpenAI-compatible endpoints such as Qwen text-embedding-v3).
        embedder_model: Optional model id passed to the embedder backend.
        embedder_dim: Vector dimensionality (used by ``fake`` and as a
            pre-load hint for other backends).
        embedder_dimensions: Output size for embedders that support flexible
            dimensions (Qwen text-embedding-v3, OpenAI text-embedding-3-*).
        llm: Optional LLM backend name — ``"fake"``, ``"deepseek"`` /
            ``"openai``" / ``"openai-compat"``. Used by consolidation.
        llm_model: Optional LLM model id (e.g. ``"deepseek-v4-flash"``).
        llm_base_url: Optional base URL for OpenAI-compatible LLM endpoints.
        namespace: Isolation key (e.g. ``"user:123"``). All reads/writes must
            be scoped to a namespace so users/sessions never leak into each
            other.
        working_max_messages: Sliding-window cap on messages (None = unbounded).
        working_max_tokens: Token budget for working memory (None = unbounded).
        echo_sql: Echo SQL statements (debugging).
        extra: Free-form bag for provider-specific options.
    """

    sqlite_url: str = "sqlite:///./memoria.db"
    chroma_path: str = "./.chroma"
    vector_store: str = "memory"
    vector_collection: str = "memoria"
    embedder: str = "fake"
    embedder_model: str | None = None
    embedder_dim: int = 384
    embedder_dimensions: int | None = None
    llm: str | None = None
    llm_model: str | None = None
    llm_base_url: str | None = None
    namespace: str = "default"
    working_max_messages: int | None = None
    working_max_tokens: int | None = None
    echo_sql: bool = False
    extra: dict[str, Any] = field(default_factory=dict)
