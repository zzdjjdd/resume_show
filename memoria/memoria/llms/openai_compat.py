"""OpenAI-compatible chat LLM — works with DeepSeek, DashScope, etc.

Credentials come from the constructor or environment and are never persisted:
    api_key  <- arg > LLM_API_KEY > DEEPSEEK_API_KEY > OPENAI_API_KEY
    base_url <- arg > LLM_BASE_URL > DEEPSEEK_BASE_URL > OPENAI_BASE_URL
Point ``base_url``/``model`` at DeepSeek (``deepseek-v4-flash``) or any
OpenAI-compatible chat endpoint.
"""

from __future__ import annotations

import os
from typing import Any

from ..errors import LLMError
from .base import LLM


class OpenAICompatLLM(LLM):
    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 512,
        **_: Any,
    ) -> None:
        self._model = model or "deepseek-chat"
        self._api_key = (
            api_key
            or os.environ.get("LLM_API_KEY")
            or os.environ.get("DEEPSEEK_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
        )
        self._base_url = (
            base_url
            or os.environ.get("LLM_BASE_URL")
            or os.environ.get("DEEPSEEK_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
        )
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._client: Any = None

    def _load(self) -> Any:
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:  # pragma: no cover - depends on env
                raise LLMError(
                    "openai is not installed. Run: pip install 'memoria[openai]'"
                ) from exc
            if not self._api_key:
                raise LLMError(
                    "LLM API key missing (set LLM_API_KEY or DEEPSEEK_API_KEY)."
                )
            kwargs: dict[str, Any] = {"api_key": self._api_key}
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = OpenAI(**kwargs)
        return self._client

    def complete(self, prompt: str, system: str | None = None) -> str:
        return self.chat([{"role": "user", "content": prompt}], system=system)

    def chat(self, messages: list[dict[str, str]], system: str | None = None) -> str:
        content, _tool_calls = self.chat_with_tools(messages, tools=None, system=system)
        return content or ""

    def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system: str | None = None,
    ) -> tuple[str | None, list[dict[str, Any]] | None]:
        client = self._load()
        payload: list[dict[str, Any]] = []
        if system:
            payload.append({"role": "system", "content": system})
        payload.extend(messages)
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": payload,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
        resp = client.chat.completions.create(**kwargs)
        message = resp.choices[0].message
        tool_calls: list[dict[str, Any]] | None = None
        raw_calls = getattr(message, "tool_calls", None)
        if raw_calls:
            tool_calls = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in raw_calls
            ]
        return message.content, tool_calls
