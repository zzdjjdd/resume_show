"""Memory — the single public facade.

All interaction with the memory system goes through this class. Providers
(embedder, later LLM), the vector store, and storage engines are injected /
resolved here so the rest of the codebase never imports concrete backends.

Implemented: working memory, episodic / semantic / procedural stores, hybrid
cross-layer retrieval (RRF + strength re-rank), consolidation and forgetting,
and prompt-context assembly.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from .config import Config
from .consolidation.consolidator import Consolidator
from .consolidation.forgetting import Forgetting
from .db.session import init_db as _init_db
from .db.session import make_engine, make_sessionmaker
from .embedders.base import Embedder
from .embedders.factory import get_embedder
from .errors import MemoriaError
from .llms.base import LLM
from .llms.factory import get_llm
from .retrieval.retriever import Retriever
from .stores.base import MemoryRecord
from .stores.episodic import EpisodicStore
from .stores.procedural import ProceduralStore
from .stores.semantic import SemanticStore
from .stores.working import WorkingMemory
from .vector.base import VectorStore
from .vector.factory import get_vector_store

CHAT_SYSTEM = (
    "你是 Memoria，一个拥有长期记忆的 AI 助手。"
    "你会参考提供的【相关长期记忆】来个性化回答，记住并呼应用户的偏好、经历与习惯。"
    "回答简洁、自然、友好。"
)


class Memory:
    def __init__(
        self,
        config: Config | None = None,
        *,
        embedder: Embedder | None = None,
        vector_store: VectorStore | None = None,
        llm: LLM | None = None,
    ) -> None:
        self.config = config or Config()
        self._embedder = embedder or get_embedder(
            self.config.embedder,
            model=self.config.embedder_model,
            dim=self.config.embedder_dim,
            dimensions=self.config.embedder_dimensions,
        )
        self._llm: LLM | None = llm or (
            get_llm(
                self.config.llm,
                model=self.config.llm_model,
                base_url=self.config.llm_base_url,
            )
            if self.config.llm
            else None
        )
        self._vector = vector_store or get_vector_store(
            self.config.vector_store,
            path=self.config.chroma_path,
            collection=self.config.vector_collection,
        )
        self._engine = make_engine(self.config)
        self._sessionmaker = make_sessionmaker(self._engine)

        self.working = WorkingMemory(
            max_messages=self.config.working_max_messages,
            max_tokens=self.config.working_max_tokens,
        )
        self._episodic = EpisodicStore(
            self._sessionmaker, self._vector, self._embedder, self.config.namespace
        )
        self._semantic = SemanticStore(
            self._sessionmaker, self._vector, self._embedder, self.config.namespace
        )
        self._procedural = ProceduralStore(
            self._sessionmaker, self._vector, self._embedder, self.config.namespace
        )
        self._retriever = Retriever(
            {
                "episodic": self._episodic,
                "semantic": self._semantic,
                "procedural": self._procedural,
            }
        )
        self._consolidator = Consolidator(
            self._episodic, self._semantic, self.working, llm=self._llm
        )
        self._forgetting = Forgetting(self._episodic, self._semantic)
        self._recall_calls = 0
        self._recall_hits = 0

    # ---- introspection ----

    @property
    def embedder(self) -> Embedder:
        return self._embedder

    @property
    def vector_store(self) -> VectorStore:
        return self._vector

    @property
    def llm(self) -> LLM | None:
        return self._llm

    @property
    def namespace(self) -> str:
        return self.config.namespace

    def session(self) -> Session:
        """Open a new DB session (caller is responsible for closing it)."""
        return self._sessionmaker()

    def init_db(self) -> None:
        """Create all tables (tests/dev). Production uses Alembic."""
        _init_db(self._engine)

    # ---- write ----

    def remember_event(
        self,
        content: str,
        importance: float = 0.5,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Record an event into episodic memory; returns its id."""
        return self._episodic.add(
            content, importance=importance, session_id=session_id, metadata=metadata
        )

    def upsert_fact(
        self,
        subject: str,
        fact: str,
        confidence: float = 0.5,
        source_episode_ids: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Insert or merge a stable fact into semantic memory; returns its id."""
        return self._semantic.upsert(
            subject,
            fact,
            confidence=confidence,
            source_episode_ids=source_episode_ids,
            metadata=metadata,
        )

    def record_procedure(self, trigger: str, steps: list[str]) -> str:
        """Record a how-to routine into procedural memory; returns its id."""
        return self._procedural.add(trigger, steps)

    def reinforce_procedure(self, record_id: str, success: bool) -> bool:
        """Reinforce (or down-weight) a procedure after use."""
        return self._procedural.reinforce(record_id, success)

    # ---- retrieve ----

    def recall(
        self,
        query: str,
        layers: list[str] | None = None,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[MemoryRecord]:
        """Cross-layer hybrid retrieval (vector recall -> RRF -> strength re-rank)."""
        self._recall_calls += 1
        records = self._retriever.recall(query, layers=layers, top_k=top_k, filters=filters)
        if records:
            self._recall_hits += 1
        return records

    def snapshot(self) -> dict[str, Any]:
        """A plain-data view of every layer (used by the web API / debugging)."""
        return {
            "working": [{"role": m.role, "content": m.content} for m in self.working.messages],
            "episodic": [
                {
                    "id": r.id,
                    "content": r.content,
                    "importance": r.importance,
                    "access_count": r.access_count or 0,
                    "created_at": str(r.created_at),
                }
                for r in self._episodic.list_all()
            ],
            "semantic": [
                {
                    "id": r.id,
                    "subject": r.subject,
                    "fact": r.fact,
                    "confidence": r.confidence,
                }
                for r in self._semantic.list_all()
            ],
            "procedural": [
                {"id": r.id, "trigger": r.trigger, "steps": r.steps or []}
                for r in self._procedural.list_all()
            ],
        }

    def build_context(self, query: str | None = None, token_budget: int = 1500) -> str:
        """Assemble working memory (+ recalled long-term memories) for prompt injection."""
        parts: list[str] = []
        if len(self.working):
            parts.append("[工作记忆]\n" + self.working.render())
        if query:
            records = self.recall(query, top_k=5)
            if records:
                lines = "\n".join(f"- [{r.layer}] {r.content}" for r in records)
                parts.append("[长期记忆]\n" + lines)
        text = "\n\n".join(parts)
        max_chars = token_budget * 4  # approx_token_count ~ 4 chars/token
        return text[:max_chars]

    # ---- conversation ----

    def chat(self, message: str, top_k: int = 5, consolidate: bool = True) -> dict[str, Any]:
        """Chat with memory: recall relevant long-term memories, reply via the
        LLM, then store the exchange and (optionally) distill new facts."""
        self.working.append("user", message)
        recalled = self.recall(message, top_k=top_k)
        memory_lines = [f"- [{r.layer}] {r.content}" for r in recalled]
        system = CHAT_SYSTEM
        if memory_lines:
            system += "\n\n【相关长期记忆（供参考）】\n" + "\n".join(memory_lines)

        if self._llm is None:
            reply = "（未配置 LLM，暂不能对话。请设置 Config.llm 或环境变量 MEMORIA_LLM。）"
        else:
            messages = [{"role": m.role, "content": m.content} for m in self.working.messages]
            try:
                reply = self._llm.chat(messages, system=system)
            except MemoriaError as exc:
                reply = f"（LLM 调用失败：{exc}）"

        self.working.append("assistant", reply)
        self.remember_event(f"用户: {message} ｜ 助手: {reply}", importance=0.6)
        distilled = 0
        if consolidate and self._llm is not None:
            distilled = self.consolidate()["facts_distilled"]
        return {"reply": reply, "recalled": len(recalled), "distilled_facts": distilled}

    # ---- consolidate & forget ----

    def consolidate(self) -> dict[str, int]:
        """Distill episodic -> semantic facts (non-destructive, idempotent)."""
        return {"facts_distilled": self._consolidator.distill_facts()}

    def flush_working(self) -> str | None:
        """Summarize working memory into an episodic event and clear the window."""
        return self._consolidator.summarize_working(clear=True)

    def forget(self, threshold: float = 0.05, max_keep: int | None = None) -> int:
        """Evict decayed episodic + semantic memories. Returns number removed."""
        return self._forgetting.forget(threshold=threshold, max_keep=max_keep)

    # ---- governance (M4) ----

    def stats(self) -> dict[str, Any]:
        """Observability: per-layer counts plus retrieval hit-rate."""
        calls = self._recall_calls
        return {
            "namespace": self.namespace,
            "embedder": self.config.embedder,
            "llm": self.config.llm or "none",
            "vector_store": self.config.vector_store,
            "counts": {
                "working": len(self.working),
                "episodic": self._episodic.count(),
                "semantic": self._semantic.count(),
                "procedural": self._procedural.count(),
            },
            "retrieval": {
                "calls": calls,
                "hits": self._recall_hits,
                "hit_rate": (self._recall_hits / calls) if calls else 0.0,
            },
        }

    def export(self, path: str | None = None) -> dict[str, Any]:
        """Export the whole namespace as JSON, optionally written to ``path``."""
        data = {"namespace": self.namespace, "layers": self.snapshot()}
        if path is not None:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
        return data

    def delete_where(
        self,
        subject: str | None = None,
        fact_contains: str | None = None,
        content_contains: str | None = None,
        trigger_contains: str | None = None,
    ) -> dict[str, int]:
        """Delete matching memories across layers (and their vectors).

        Only layers whose conditions are supplied are touched; calling with no
        conditions wipes the entire namespace (right to be forgotten).
        """
        wipe = (
            subject is None
            and fact_contains is None
            and content_contains is None
            and trigger_contains is None
        )
        episodic = semantic = procedural = 0
        if wipe or content_contains is not None:
            episodic = len(self._episodic.delete_where(content_contains=content_contains))
        if wipe or subject is not None or fact_contains is not None:
            semantic = len(
                self._semantic.delete_where(subject=subject, fact_contains=fact_contains)
            )
        if wipe or trigger_contains is not None:
            procedural = len(
                self._procedural.delete_where(trigger_contains=trigger_contains)
            )
        return {
            "episodic": episodic,
            "semantic": semantic,
            "procedural": procedural,
            "total": episodic + semantic + procedural,
        }
