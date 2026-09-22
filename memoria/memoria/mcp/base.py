"""MCP tool-server contract + conversion to OpenAI function-calling format."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class MCPToolServer(ABC):
    """A connection to an MCP server that exposes callable tools."""

    @abstractmethod
    async def list_tools(self) -> list[Any]:
        """Return tool descriptors (each with name / description / inputSchema)."""

    @abstractmethod
    async def call_tool_text(self, name: str, arguments: dict[str, Any]) -> str:
        """Invoke a tool and return its result rendered as text."""

    async def close(self) -> None:
        """Release the connection (no-op by default)."""
        return None


def to_openai_tools(tools: list[Any]) -> list[dict[str, Any]]:
    """Convert MCP tool descriptors into OpenAI function-calling schema."""
    converted: list[dict[str, Any]] = []
    for tool in tools:
        converted.append(
            {
                "type": "function",
                "function": {
                    "name": getattr(tool, "name", ""),
                    "description": getattr(tool, "description", "") or "",
                    "parameters": getattr(tool, "inputSchema", None)
                    or {"type": "object", "properties": {}},
                },
            }
        )
    return converted
