"""Deterministic fake LLM for tests and offline development."""

from __future__ import annotations

from typing import Any


class FakeLLM:
    """Returns canned responses in order; records prompts and the last system
    prompt it received. Implements the :class:`~memoria.llms.base.LLM` interface
    structurally (both ``complete`` and ``chat``)."""

    def __init__(
        self,
        responses: list[str] | None = None,
        chat_tool_script: list[tuple[str | None, list[dict[str, Any]] | None]] | None = None,
        **_: Any,
    ) -> None:
        self._responses = list(responses or [])
        self._tool_script = list(chat_tool_script or [])
        self.calls: list[str] = []
        self.last_system: str | None = None

    def _next(self) -> str:
        if self._responses:
            return self._responses.pop(0)
        return ""

    def complete(self, prompt: str, system: str | None = None) -> str:
        self.calls.append(prompt)
        self.last_system = system
        return self._next()

    def chat(self, messages: list[dict[str, str]], system: str | None = None) -> str:
        self.last_system = system
        last = messages[-1]["content"] if messages else ""
        self.calls.append(last)
        return self._next()

    def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system: str | None = None,
    ) -> tuple[str | None, list[dict[str, Any]] | None]:
        self.last_system = system
        last = messages[-1]["content"] if messages else ""
        self.calls.append(last)
        if self._tool_script:
            return self._tool_script.pop(0)
        return self._next(), None
