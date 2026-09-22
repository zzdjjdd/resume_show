"""Working memory: the ephemeral, in-process context of the current session.

A sliding window bounded by message count and/or a token budget. Oldest
messages are dropped first. The token counter is pluggable — the default is a
lightweight heuristic so nothing external is required; swap in a real tokenizer
(e.g. tiktoken) via the ``token_counter`` argument.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Message:
    """A single turn in working memory."""

    role: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


def approx_token_count(text: str) -> int:
    """Rough ~4-chars-per-token heuristic. Deterministic and dependency-free."""
    return max(1, len(text) // 4)


class WorkingMemory:
    def __init__(
        self,
        max_messages: int | None = None,
        max_tokens: int | None = None,
        token_counter: Callable[[str], int] = approx_token_count,
    ) -> None:
        self.max_messages = max_messages
        self.max_tokens = max_tokens
        self._count_tokens = token_counter
        self._messages: list[Message] = []

    def append(self, role: str, content: str, **metadata: Any) -> Message:
        message = Message(role=role, content=content, metadata=metadata)
        self._messages.append(message)
        self._trim()
        return message

    @property
    def messages(self) -> list[Message]:
        return list(self._messages)

    def __len__(self) -> int:
        return len(self._messages)

    def token_count(self) -> int:
        return sum(self._count_tokens(m.content) for m in self._messages)

    def clear(self) -> None:
        self._messages.clear()

    def render(self) -> str:
        """Render as ``role: content`` lines for prompt injection."""
        return "\n".join(f"{m.role}: {m.content}" for m in self._messages)

    def _trim(self) -> None:
        if self.max_messages is not None:
            while len(self._messages) > self.max_messages:
                self._messages.pop(0)
        if self.max_tokens is not None:
            # Always keep at least the most recent message.
            while len(self._messages) > 1 and self.token_count() > self.max_tokens:
                self._messages.pop(0)
