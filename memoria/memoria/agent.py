"""Tool-using conversational agent: memory + LLM + MCP tools.

Run loop per user message:
1. append to working memory and recall relevant long-term memories;
2. ask the LLM with those memories (and MCP tools, if any) available;
3. if the LLM requests tool calls, execute them via the MCP server and feed the
   results back — repeat until a final answer (bounded by ``max_tool_rounds``);
4. store the exchange into episodic memory and distill new facts.
"""

from __future__ import annotations

import json
from typing import Any

from .manager import CHAT_SYSTEM, Memory
from .mcp.base import MCPToolServer, to_openai_tools


class Agent:
    def __init__(
        self,
        memory: Memory,
        mcp: MCPToolServer | None = None,
        max_tool_rounds: int = 6,
    ) -> None:
        self._memory = memory
        self._mcp = mcp
        self._max = max_tool_rounds

    async def run(
        self,
        message: str,
        top_k: int = 5,
        consolidate: bool = True,
    ) -> dict[str, Any]:
        mem = self._memory
        mem.working.append("user", message)
        recalled = mem.recall(message, top_k=top_k)
        system = CHAT_SYSTEM
        memory_lines = [f"- [{r.layer}] {r.content}" for r in recalled]
        if memory_lines:
            system += "\n\n【相关长期记忆（供参考）】\n" + "\n".join(memory_lines)

        llm = mem.llm
        if llm is None:
            reply = "（未配置 LLM，暂不能对话。请设置 Config.llm 或环境变量 MEMORIA_LLM。）"
            mem.working.append("assistant", reply)
            return {
                "reply": reply,
                "recalled": len(recalled),
                "distilled_facts": 0,
                "tools_called": [],
            }

        tools = None
        if self._mcp is not None:
            mcp_tools = await self._mcp.list_tools()
            if mcp_tools:
                tools = to_openai_tools(mcp_tools)

        messages: list[dict[str, Any]] = [
            {"role": m.role, "content": m.content} for m in mem.working.messages
        ]
        content: str | None = ""
        tools_called: list[str] = []
        for _ in range(self._max):
            content, tool_calls = llm.chat_with_tools(messages, tools=tools, system=system)
            if not tool_calls:
                break
            messages.append(
                {"role": "assistant", "content": content or "", "tool_calls": tool_calls}
            )
            for tc in tool_calls:
                name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                result_text = await self._mcp.call_tool_text(name, args) if self._mcp else ""
                tools_called.append(name)
                messages.append(
                    {"role": "tool", "tool_call_id": tc.get("id", ""), "content": result_text}
                )

        reply = content or ""
        mem.working.append("assistant", reply)
        mem.remember_event(f"用户: {message} ｜ 助手: {reply}", importance=0.6)
        distilled = 0
        if consolidate:
            distilled = mem.consolidate()["facts_distilled"]
        return {
            "reply": reply,
            "recalled": len(recalled),
            "distilled_facts": distilled,
            "tools_called": tools_called,
        }
