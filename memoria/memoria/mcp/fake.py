"""Fake MCP tool server for offline tests / development."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .base import MCPToolServer


class FakeTool:
    """Minimal stand-in for an MCP tool descriptor."""

    def __init__(
        self,
        name: str,
        description: str = "",
        input_schema: dict[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.inputSchema = input_schema or {"type": "object", "properties": {}}


class FakeMCPToolServer(MCPToolServer):
    """Returns configured tools and canned (or callable) results."""

    def __init__(
        self,
        tools: list[FakeTool] | None = None,
        results: dict[str, str | Callable[[dict[str, Any]], str]] | None = None,
    ) -> None:
        self._tools = list(tools or [])
        self._results: dict[str, Any] = dict(results or {})
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def list_tools(self) -> list[FakeTool]:
        return list(self._tools)

    async def call_tool_text(self, name: str, arguments: dict[str, Any]) -> str:
        self.calls.append((name, arguments))
        handler = self._results.get(name, "")
        return handler(arguments) if callable(handler) else str(handler)
