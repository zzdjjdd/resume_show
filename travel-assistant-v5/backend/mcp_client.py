"""通用 MCP(Model Context Protocol)客户端。
支持 JSON-RPC 2.0 over HTTP,兼容流式(SSE)与非流式响应。
通过运行时 list_tools 动态发现工具,无需硬编码 tool 名。
"""
import json
import uuid
from typing import Any, Dict, List, Optional, Tuple

import httpx


# JSON-RPC 2.0 协议版本
PROTOCOL_VERSION = "2024-11-05"

# 客户端能力声明(本项目只消费 tools/list + tools/call)
CLIENT_CAPABILITIES = {
    "sampling": {},
    "roots": {"listChanged": False},
}


class MCPError(Exception):
    """MCP 协议层错误(JSON-RPC error / 网络错误 / 协议错误)"""


class MCPClient:
    """通用 MCP 客户端。

    设计要点:
    - 不硬编码任何 tool 名,运行时调 tools/list 自动发现
    - 支持两种响应形态:单一 JSON-RPC result / SSE 流(每行一个 event)
    - URL 本身可携带鉴权 token(无需 header)
    - initialize 失败时设 enabled=False,不抛异常
    """

    def __init__(self, server_url: str, timeout: int = 30):
        self.server_url = (server_url or "").rstrip("/")
        self.timeout = timeout
        self._session_id: Optional[str] = None
        self._tools: List[Dict[str, Any]] = []  # OpenAI function-call 格式
        self._raw_tools: List[Dict[str, Any]] = []  # MCP 原始 tools/list
        self._initialized: bool = False
        self._init_error: Optional[str] = None
        self.server_info: Dict[str, Any] = {}  # initialize 响应中的 serverInfo

    # ------------------------------------------------------------------
    # 公共属性
    # ------------------------------------------------------------------
    @property
    def enabled(self) -> bool:
        return self._initialized and bool(self._tools)

    @property
    def init_error(self) -> Optional[str]:
        return self._init_error

    @property
    def tool_names(self) -> List[str]:
        return [t.get("function", {}).get("name", "") for t in self._tools]

    # ------------------------------------------------------------------
    # 初始化:POST initialize + tools/list
    # ------------------------------------------------------------------
    async def initialize(self) -> bool:
        """初始化会话:发送 initialize 握手,再 list_tools。失败时记录错误但不抛。"""
        if not self.server_url:
            self._init_error = "server_url 为空"
            return False
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # 1) initialize
                init_params: Dict[str, Any] = {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": CLIENT_CAPABILITIES,
                    "clientInfo": {"name": "ai-travel-assistant", "version": "1.0.0"},
                }
                init_payload = {
                    "jsonrpc": "2.0",
                    "id": self._new_id(),
                    "method": "initialize",
                    "params": init_params,
                }
                init_resp = await self._post_jsonrpc(client, init_payload)
                if "error" in init_resp:
                    raise MCPError(f"initialize error: {init_resp['error']}")
                result = init_resp.get("result", {})
                self.server_info = result.get("serverInfo", {}) or {}
                # 记 session id(MCP 2024-11-05 通过 header Mcp-Session-Id 传递)
                # httpx response.headers 我们拿不到,这里从 result 中提取如服务端返回
                proto_ver = result.get("protocolVersion")
                if proto_ver and proto_ver != PROTOCOL_VERSION:
                    # 协议版本不匹配,但仍尝试 list_tools
                    pass

                # 2) notifications/initialized(无 response)
                notif_payload = {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                }
                try:
                    await self._post_jsonrpc(client, notif_payload, expect_result=False)
                except Exception:
                    pass  # 通知类消息无响应,忽略错误

                # 3) tools/list
                list_payload = {
                    "jsonrpc": "2.0",
                    "id": self._new_id(),
                    "method": "tools/list",
                }
                list_resp = await self._post_jsonrpc(client, list_payload)
                if "error" in list_resp:
                    raise MCPError(f"tools/list error: {list_resp['error']}")
                self._raw_tools = (list_resp.get("result", {}) or {}).get("tools", []) or []
                self._tools = [self._to_openai_format(t) for t in self._raw_tools]
                self._initialized = True
                self._init_error = None
                return True
        except Exception as e:
            self._initialized = False
            self._init_error = f"{type(e).__name__}: {e}"
            return False

    # ------------------------------------------------------------------
    # 公共方法:列出工具 + 调用工具
    # ------------------------------------------------------------------
    def list_tools(self, refresh: bool = False) -> List[Dict[str, Any]]:
        """同步版:仅返回 _initialized=True 时的缓存;未初始化则 []。

        ChatAgent._gather_tools() 在 chat/stream_chat 主循环里被同步调用,
        因此保留同步接口。异步初始化在 app lifespan 里完成。
        """
        return list(self._tools) if self._initialized else []  # type: ignore[return-value]  -- 编译器不知 _initialized 已被 initialize 设置

    async def list_tools_async(self, refresh: bool = False) -> List[Dict[str, Any]]:
        """异步版,可在未初始化时触发 initialize。refresh=True 强制重拉。"""
        if refresh or not self._initialized:
            ok = await self.initialize()
            if not ok:
                return []
        return list(self._tools)

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """调用指定 tool。返回 {success, data, error}。"""
        if not self._initialized:
            return {"success": False, "error": f"MCP 未初始化: {self._init_error or '请先启用并测试连接'}"}
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": self._new_id(),
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments or {}},
            }
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await self._post_jsonrpc(client, payload)
            if "error" in resp:
                return {"success": False, "error": str(resp["error"])}
            result = resp.get("result", {}) or {}
            # MCP 2024-11-05:result 形如 {content: [{type: 'text', text: '...'}], isError: false}
            return self._normalize_call_result(result)
        except Exception as e:
            return {"success": False, "error": f"{type(e).__name__}: {e}"}

    # ------------------------------------------------------------------
    # 摘要:通用兜底,不需要认识具体 tool
    # ------------------------------------------------------------------
    def summarize_result(self, name: str, result: Dict[str, Any]) -> str:
        """把工具结果压成中文摘要。失败 → 错误说明;成功 → 取 data 的关键字段。"""
        if not result.get("success"):
            err = result.get("error", "未知错误")
            return f"调用失败: {err}"
        data = result.get("data")
        if data is None:
            return "(无返回数据)"
        # data 可能是 dict / list / str
        if isinstance(data, str):
            return data[:600] + ("…" if len(data) > 600 else "")
        if isinstance(data, list):
            if not data:
                return "(空列表)"
            lines = [f"共 {len(data)} 条:"]
            for i, item in enumerate(data[:5], 1):
                if isinstance(item, dict):
                    title = item.get("name") or item.get("title") or item.get("id") or f"#{i}"
                    sub = item.get("address") or item.get("description") or item.get("text") or ""
                    if isinstance(sub, str) and len(sub) > 80:
                        sub = sub[:80] + "…"
                    lines.append(f"  {i}. {title}" + (f" — {sub}" if sub else ""))
                else:
                    lines.append(f"  {i}. {str(item)[:80]}")
            return "\n".join(lines)
        if isinstance(data, dict):
            return self._summarize_dict(data, depth=0)
        return str(data)[:600]

    def _summarize_dict(self, d: Dict[str, Any], depth: int) -> str:
        """递归摘要 dict,前 8 个键,深度不超过 2。"""
        if depth >= 2:
            return json.dumps(d, ensure_ascii=False)[:200]
        lines = []
        for k, v in list(d.items())[:8]:
            if isinstance(v, str):
                v_disp = v if len(v) <= 120 else v[:120] + "…"
                lines.append(f"{k}: {v_disp}")
            elif isinstance(v, (int, float, bool)):
                lines.append(f"{k}: {v}")
            elif isinstance(v, list):
                lines.append(f"{k}: [list × {len(v)}]")
            elif isinstance(v, dict):
                lines.append(f"{k}: {self._summarize_dict(v, depth + 1)}")
            else:
                lines.append(f"{k}: {str(v)[:80]}")
        return "; ".join(lines)

    # ------------------------------------------------------------------
    # 内部:HTTP/JSON-RPC 通信
    # ------------------------------------------------------------------
    def _new_id(self) -> str:
        return uuid.uuid4().hex

    async def _post_jsonrpc(
        self,
        client: httpx.AsyncClient,
        payload: Dict[str, Any],
        expect_result: bool = True,
    ) -> Dict[str, Any]:
        """POST JSON-RPC 到 server_url,自动处理 SSE 流式与非流式响应。

        副作用:从响应 header 提取 mcp-session-id,保存到 self._session_id。
        后续请求会自动带 Mcp-Session-Id 头。
        """
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        # 不传 session id(本项目简化为无状态)
        resp = await client.post(self.server_url, json=payload, headers=headers)

        # 提取并保存 session id(MCP 2024-11-05 通过 response header 返回)
        sid = resp.headers.get("mcp-session-id") or resp.headers.get("Mcp-Session-Id")
        if sid and not self._session_id:
            self._session_id = sid

        resp.raise_for_status()
        ct = (resp.headers.get("content-type") or "").lower()
        body_text = resp.text

        # SSE 形态:逐行 event:
        if "text/event-stream" in ct or body_text.lstrip().startswith("event:"):
            return self._parse_sse_response(body_text, expect_result=expect_result)

        # 普通 JSON 形态
        try:
            data = resp.json()
        except Exception as e:
            raise MCPError(f"响应不是合法 JSON: {e}; 原文: {body_text[:200]}")
        if not expect_result:
            return {}
        return data

    def _parse_sse_response(self, body: str, expect_result: bool) -> Dict[str, Any]:
        """从 SSE 文本里抽出最后一个含 'data:' 的 JSON-RPC 消息。"""
        last_data: Optional[str] = None
        for line in body.splitlines():
            if line.startswith("data:"):
                last_data = line[5:].strip()
        if not last_data:
            if not expect_result:
                return {}
            raise MCPError(f"SSE 响应无 data 行: {body[:200]}")
        if last_data == "[DONE]":
            if not expect_result:
                return {}
            raise MCPError("SSE 响应收到 [DONE]")
        try:
            return json.loads(last_data)
        except Exception as e:
            raise MCPError(f"SSE data 不是合法 JSON: {e}; 原文: {last_data[:200]}")

    # ------------------------------------------------------------------
    # 内部:格式转换
    # ------------------------------------------------------------------
    def _to_openai_format(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """MCP tool → OpenAI function-call 格式。"""
        name = raw.get("name", "")
        desc = raw.get("description", "")
        input_schema = raw.get("inputSchema") or raw.get("input_schema") or {"type": "object", "properties": {}}
        # OpenAI 的 parameters 期望是 JSON Schema
        if "type" not in input_schema:
            input_schema = {**input_schema, "type": "object"}
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": desc,
                "parameters": input_schema,
            },
        }

    def _normalize_call_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """把 MCP 2024-11-05 的 tools/call result 转成项目内部 {success, data, error}。"""
        is_error = bool(result.get("isError"))
        content = result.get("content", []) or []
        if is_error:
            # content 可能是 [{type:'text', text:'error msg'}]
            err_text = self._extract_text(content) or "工具返回 isError=true"
            return {"success": False, "error": err_text}
        # 成功:合并所有 content 的 text 字段
        text_pieces: List[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            t = item.get("text")
            if isinstance(t, str):
                text_pieces.append(t)
        merged = "\n".join(text_pieces).strip()
        # 尝试把 merged 解析为 JSON,如果能就当 dict/list 暴露,否则保留 str
        data: Any = merged
        if merged:
            try:
                data = json.loads(merged)
            except Exception:
                pass
        return {"success": True, "data": data, "raw": result}

    def _extract_text(self, content: List[Any]) -> str:
        out: List[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                out.append(item["text"])
        return "\n".join(out).strip()
