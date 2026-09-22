"""日记聊天智能体：支持工具调用 + 模型思考过程展示"""
import json
import uuid
from copy import deepcopy
from typing import Any, Dict, List, AsyncIterator, Optional
from .llm_client import LLMClient
from .amap_mcp import AmapMCPClient, summarize_amap_result
from .mcp_client import MCPClient


SYSTEM_PROMPT_CHAT = """你是「AI智行助手」，一位专业、友好且富有洞察力的出行智能管家。

【你的能力】
- 熟悉中国大多数城市的交通、景点、餐饮、住宿。
- 可以根据用户实际需要，主动调用高德地图 MCP 工具来获取：路径规划、POI 搜索、距离测量、天气查询、地理编码等实时数据。
- 当用户在设置中启用了外部 MCP 服务时,你也可以调用其提供的工具(例如:12306 高铁票查询、酒店查询等)。这类工具名以 `mc_` 前缀开头,系统已自动接入。
- 也可以回答一般生活问题（如问候、闲聊、咨询等）。

【回答风格】
1. 使用中文。
2. 简洁但信息丰富。涉及出行/位置时，主动调用相应工具，而不是凭空猜测。
3. 当你调用了工具时，请明确告知用户：「我调用了 XXX 工具，获得了 XXX 数据」。
4. 输出使用 Markdown 格式，便于前端展示：列表、引用、表格、链接都可以用。
5. 在数据丰富的时候，建议「下一步」可选项，让对话可以延续。

【特别注意】
- 用户要求「路线/距离/POI/天气/地址解析」等场景时，**必须调用相应工具**而非猜测。
- 用户要求「高铁/动车/火车票/酒店/住宿」等场景时,优先调用 `mc_` 前缀的外部 MCP 工具(若已启用)。
- 如果工具调用失败，告知用户失败原因并建议替代方案。
- 不要捏造具体的经纬度或地址。
"""


def extract_reasoning(msg: Dict[str, Any]) -> str:
    """从 LLM 响应 message 中抽出思考过程文本。
    支持多种风格：
    - MiniMax / 部分本地代理：reasoning_details 列表 / 字符串
    - OpenAI 风格：reasoning 字段
    - Anthropic via proxy：reasoning_content
    """
    if not isinstance(msg, dict):
        return ""
    rd = msg.get("reasoning_details")
    if isinstance(rd, list) and rd:
        texts = []
        for x in rd:
            if isinstance(x, dict):
                t = x.get("text") or x.get("reasoning") or ""
                if t: texts.append(str(t))
            elif isinstance(x, str):
                texts.append(x)
        return "\n\n".join([t for t in texts if t])
    if isinstance(rd, str):
        return rd
    r = msg.get("reasoning")
    if isinstance(r, str):
        return r
    rc = msg.get("reasoning_content")
    if isinstance(rc, str):
        return rc
    return ""


class ChatAgent:
    """日常聊天 + 工具调用 + 思考过程"""

    # MCP 工具名前缀(避免与 amap 工具冲突)
    MCP_TOOL_PREFIX = "mc_"

    def __init__(
        self,
        llm: LLMClient,
        amap: AmapMCPClient,
        mcp: Optional[MCPClient] = None,
        max_tool_rounds: int = 6,
    ):
        self.llm = llm
        self.amap = amap
        self.mcp = mcp
        self.max_tool_rounds = max_tool_rounds

    # ------------------------------------------------------------------
    # 工具收集 / 路由 / 摘要
    # ------------------------------------------------------------------
    def _gather_tools(self) -> Optional[List[Dict[str, Any]]]:
        """合并 amap + MCP 工具。MCP 工具名加 mc_ 前缀。"""
        tools: List[Dict[str, Any]] = []
        if self.amap.api_key:
            tools.extend(self.amap.tools())
        if self.mcp and self.mcp.enabled:
            for t in self.mcp.list_tools():
                t = deepcopy(t)
                fn = t.get("function", {})
                orig_name = fn.get("name", "")
                if orig_name and not orig_name.startswith(self.MCP_TOOL_PREFIX):
                    fn["name"] = f"{self.MCP_TOOL_PREFIX}{orig_name}"
                # 加个 [MCP] 前缀方便 LLM 区分来源
                desc = fn.get("description", "")
                if desc and "[MCP]" not in desc:
                    fn["description"] = f"[MCP] {desc}"
                tools.append(t)
        return tools or None

    async def _route_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """按工具名前缀分发到 amap 或 MCP。"""
        if name.startswith(self.MCP_TOOL_PREFIX):
            if not self.mcp:
                return {"success": False, "error": "MCP 未启用"}
            return await self.mcp.call_tool(name[len(self.MCP_TOOL_PREFIX):], args)
        return await self.amap.call_tool(name, args)

    def _summarize(self, name: str, result: Dict[str, Any]) -> str:
        """按工具名前缀选择摘要器。"""
        if name.startswith(self.MCP_TOOL_PREFIX):
            if not self.mcp:
                return "MCP 未启用"
            return self.mcp.summarize_result(name[len(self.MCP_TOOL_PREFIX):], result)
        return summarize_amap_result(name, result)

    async def chat(self, history: List[Dict[str, str]], user_text: str) -> Dict[str, Any]:
        """非流式对话（保留工具调用记录）"""
        messages: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT_CHAT}]
        for h in history:
            messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": user_text})

        tools_used: List[Dict[str, Any]] = []
        reasoning_all: List[str] = []
        tools = self._gather_tools()

        for _ in range(self.max_tool_rounds):
            resp = await self.llm.chat(messages, tools=tools, stream=False, temperature=0.6)
            try:
                msg = resp["choices"][0]["message"]
            except Exception as e:
                return {"success": False, "error": str(e), "raw": resp}

            rd = extract_reasoning(msg)
            if rd:
                reasoning_all.append(rd)

            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                content = msg.get("content", "") or ""
                return {
                    "success": True,
                    "content": content,
                    "tools_used": tools_used,
                    "messages": messages,
                    "reasoning": "\n\n".join(reasoning_all),
                }

            messages.append(msg)
            for tc in tool_calls:
                fn = (tc.get("function") or {})
                name = fn.get("name", "")
                args_raw = fn.get("arguments", "{}")
                try:
                    args = json.loads(args_raw) if isinstance(args_raw, str) else (args_raw or {})
                except Exception:
                    args = {}
                result = await self._route_tool(name, args)
                summary = self._summarize(name, result)
                tools_used.append({"name": name, "arguments": args, "summary": summary, "raw": result})
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", str(uuid.uuid4())),
                    "name": name,
                    "content": json.dumps({"summary": summary, "raw": result}, ensure_ascii=False),
                })
        return {
            "success": True,
            "content": "我尝试为你查询但暂时没法获得更多内容，可以换种问法再试试。",
            "tools_used": tools_used,
            "messages": messages,
            "reasoning": "\n\n".join(reasoning_all),
        }

    async def stream_chat(self, history: List[Dict[str, str]], user_text: str) -> AsyncIterator[Dict[str, Any]]:
        """流式对话：分阶段 yield 事件
        event: 'thinking' | 'tool' | 'content' | 'done'
        - thinking：{'event': 'thinking', 'delta': str}（可多次）
        - tool：{'event': 'tool', 'name', 'arguments', 'status': 'running'|'done', 'summary'?}
        - content：{'event': 'content', 'delta': str}
        - done：{'event': 'done', 'tools_used': [...], 'reasoning': str}
        """
        messages: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT_CHAT}]
        for h in history:
            messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": user_text})

        tools_used: List[Dict[str, Any]] = []
        reasoning_all: List[str] = []
        tools = self._gather_tools()

        for _ in range(self.max_tool_rounds):
            resp = await self.llm.chat(messages, tools=tools, stream=False, temperature=0.6)
            try:
                msg = resp["choices"][0]["message"]
            except Exception as e:
                yield {"event": "done", "error": str(e)}
                return

            rd = extract_reasoning(msg)
            if rd:
                reasoning_all.append(rd)
                yield {"event": "thinking", "delta": rd}

            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                content = msg.get("content", "") or ""
                if content:
                    yield {"event": "content", "delta": content}
                yield {"event": "done", "tools_used": tools_used, "reasoning": "\n\n".join(reasoning_all)}
                return

            messages.append(msg)
            for tc in tool_calls:
                fn = (tc.get("function") or {})
                name = fn.get("name", "")
                args_raw = fn.get("arguments", "{}")
                try:
                    args = json.loads(args_raw) if isinstance(args_raw, str) else (args_raw or {})
                except Exception:
                    args = {}
                yield {"event": "tool", "name": name, "arguments": args, "status": "running"}
                result = await self._route_tool(name, args)
                summary = self._summarize(name, result)
                tools_used.append({"name": name, "arguments": args, "summary": summary, "raw": result})
                yield {"event": "tool", "name": name, "arguments": args, "status": "done", "summary": summary}
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", str(uuid.uuid4())),
                    "name": name,
                    "content": json.dumps({"summary": summary, "raw": result}, ensure_ascii=False),
                })
        yield {"event": "done", "tools_used": tools_used, "reasoning": "\n\n".join(reasoning_all)}
