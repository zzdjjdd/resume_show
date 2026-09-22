"""LLM contract for consolidation / summarization / reranking."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLM(ABC):
    """A text generator. Implementations must construct offline; the client is
    created lazily on first use."""

    @abstractmethod
    def complete(self, prompt: str, system: str | None = None) -> str:
        """Single-turn completion; returns the assistant text."""

    def chat(self, messages: list[dict[str, str]], system: str | None = None) -> str:
        """Multi-turn chat. Default folds history into a single completion;
        native chat providers should override this."""
        transcript = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
        return self.complete(transcript, system=system)

    def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system: str | None = None,
    ) -> tuple[str | None, list[dict[str, Any]] | None]:
        """Chat with optional function-calling tools.

        Returns ``(content, tool_calls)``; ``tool_calls`` is a list of
        OpenAI-format tool-call dicts when the model wants to call tools.
        Default ignores tools and folds to :meth:`chat`.
        """
        return self.chat(messages, system=system), None
