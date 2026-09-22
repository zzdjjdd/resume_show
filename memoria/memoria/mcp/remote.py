"""Remote MCP tool server over SSE (e.g. AMap hosted endpoint). Lazy import.

Connects to a hosted MCP SSE endpoint such as
``https://mcp.amap.com/sse?key=<AMAP_MAPS_API_KEY>`` using the official ``mcp``
Python SDK (installed via ``pip install mcp``). The SDK is imported lazily so
the rest of the package works without it.
"""

from __future__ import annotations

from contextlib import AsyncExitStack
from typing import Any

from ..errors import MemoriaError
from .base import MCPToolServer


class RemoteMCPToolServer(MCPToolServer):
    def __init__(self, url: str) -> None:
        self._url = url
        self._stack: AsyncExitStack | None = None
        self._session: Any = None

    async def connect(self) -> None:
        try:
            from mcp import ClientSession
            from mcp.client.sse import sse_client
        except ImportError as exc:  # pragma: no cover - depends on env
            raise MemoriaError("mcp SDK not installed. Run: pip install mcp") from exc
        stack = AsyncExitStack()
        try:
            read, write = await stack.enter_async_context(sse_client(self._url))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
        except Exception as exc:
            await stack.aclose()
            raise MemoriaError(f"Failed to connect to MCP server: {exc}") from exc
        self._stack = stack
        self._session = session

    async def list_tools(self) -> list[Any]:
        if self._session is None:
            return []
        result = await self._session.list_tools()
        return list(result.tools)

    async def call_tool_text(self, name: str, arguments: dict[str, Any]) -> str:
        if self._session is None:
            return ""
        result = await self._session.call_tool(name, arguments)
        parts: list[str] = []
        for block in getattr(result, "content", None) or []:
            text = getattr(block, "text", None)
            if text:
                parts.append(str(text))
        return "\n".join(parts)

    async def close(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()
            self._stack = None
            self._session = None
