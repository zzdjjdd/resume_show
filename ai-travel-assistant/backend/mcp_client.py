"""
通用 MCP-over-SSE 客户端（JSON-RPC 2.0）。

协议要点：
- GET <url> 带 Accept: text/event-stream，服务端持续推 SSE 事件。
- 第一个事件通常是 `event: endpoint`，`data:` 字段为 POST URL。
- 客户端把 JSON-RPC 请求 POST 到那个 endpoint；服务端用 `event: message` + `data: <jsonrpc-response>` 回送。
- 流程：initialize → notifications/initialized → tools/list → tools/call。

约定：
- 同一 server 多次调用复用同一长连接（_CLIENT_CACHE），不每个 tool call 重连。
- 所有外部 MCP 工具名前缀加 "{server_name}__"，避免与 amap 工具重名。
- 任何失败一律返回 dict（含 "error" 键），不抛异常，便于在聊天流里被自然降级。
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from concurrent.futures import Future, TimeoutError as FutTimeoutError
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

import requests

from .config import load_config

logger = logging.getLogger(__name__)


# ---------------- 常量 ----------------

PROTOCOL_VERSION = "2024-11-05"
CLIENT_INFO = {"name": "ai-zhixing-assistant", "version": "1.0.0"}

ENDPOINT_HANDSHAKE_TIMEOUT = 8.0   # 等 endpoint 事件的秒数
REQUEST_TIMEOUT = 30.0             # 单次 JSON-RPC 请求默认超时
CALL_TOOL_TIMEOUT = 60.0           # 工具调用可放宽
CONNECT_TIMEOUT = 8.0              # 初始 GET 的 connect timeout


# ---------------- MCP SSE 客户端 ----------------

class McpSseClient:
    """单个 MCP server 的 SSE 长连接客户端。"""

    def __init__(self, server_name: str, url: str) -> None:
        self.server_name = server_name
        self.url = url
        self._mode: Optional[str] = None           # None | "http" | "sse"
        self._http_url: Optional[str] = None       # Streamable HTTP endpoint（如 /mcp）
        self._session_id: Optional[str] = None     # Mcp-Session-Id header
        self._post_url: Optional[str] = None       # SSE 模式的 POST endpoint
        self._response: Optional[requests.Response] = None
        self._thread: Optional[threading.Thread] = None
        self._pending: Dict[str, Future] = {}
        self._lock = threading.Lock()
        self._initialized = False
        self._closed = False
        self._last_event_ts: float = 0.0

    # ---- 生命周期 ----

    def connect(self) -> None:
        """探测传输层：优先 Streamable HTTP（单次 POST，快）。
        只在 URL 本身是 SSE 端点（以 /sse 结尾）时，HTTP 失败才 fallback SSE。
        这样 ModelScope 这类只暴露 /mcp 的 server 不会再浪费时间连不存在的 /sse。
        """
        if self._closed:
            raise RuntimeError("client 已关闭")
        if self._mode == "http" or (self._response is not None and self._post_url):
            return

        # 1) 探测 Streamable HTTP：POST {base}/mcp initialize
        if self._try_http_mode():
            return

        # 2) 只有 URL 显式以 /sse 结尾时才 fallback SSE 传输
        if self.url.rstrip("/").endswith("/sse"):
            self._connect_sse()
            return

        # 3) 否则直接报错，不再尝试 SSE
        raise RuntimeError(
            "HTTP 模式探测失败，且 URL 非 /sse 端点，不尝试 SSE fallback。"
            "请确认 MCP server 是否支持 Streamable HTTP（POST 到 /mcp）。"
        )

    def _try_http_mode(self) -> bool:
        """探测 Streamable HTTP transport：POST initialize。"""
        # 推导 http_url：
        #   1) url 本身以 /mcp 结尾 → 直接用
        #   2) url 以 /sse 结尾 → 把末段替换为 /mcp
        #   3) 其他 → 在末尾拼 /mcp
        base = self.url.rstrip("/")
        if base.endswith("/mcp"):
            http_url = base
        elif base.endswith("/sse"):
            http_url = base[:-4] + "/mcp"
        else:
            http_url = base + "/mcp"

        body = json.dumps({
            "jsonrpc": "2.0",
            "id": "probe",
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": CLIENT_INFO,
            },
        }, ensure_ascii=False)
        try:
            r = requests.post(
                http_url,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                },
                data=body,
                timeout=4,
            )
        except requests.RequestException:
            return False

        if r.status_code != 200:
            return False
        try:
            payload = r.json()
        except ValueError:
            return False
        if not isinstance(payload, dict) or "result" not in payload:
            return False

        self._mode = "http"
        self._http_url = http_url
        self._session_id = r.headers.get("Mcp-Session-Id") or r.headers.get("mcp-session-id")
        self._initialized = True  # initialize 已完成
        # 发 notifications/initialized（不阻塞、不等响应）
        try:
            requests.post(
                http_url,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                    **({"Mcp-Session-Id": self._session_id} if self._session_id else {}),
                },
                data=json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}, ensure_ascii=False),
                timeout=4,
            )
        except requests.RequestException:
            pass
        return True

    def _connect_sse(self) -> None:
        """经典 HTTP+SSE 传输：GET 等 endpoint 事件 + 后台 reader。"""
        try:
            resp = requests.get(
                self.url,
                headers={"Accept": "text/event-stream", "Cache-Control": "no-cache"},
                stream=True,
                timeout=CONNECT_TIMEOUT,
            )
        except requests.RequestException as e:
            raise RuntimeError(f"无法连接 MCP server：{e}") from e

        if resp.status_code >= 400:
            resp.close()
            raise RuntimeError(f"MCP server 返回 HTTP {resp.status_code}")

        # iter_lines 只能有一个消费者：交给后台 reader；主线程 wait endpoint 事件
        self._mode = "sse"
        self._response = resp
        self._thread = threading.Thread(
            target=self._reader_loop, daemon=True, name=f"mcp-sse-{self.server_name}"
        )
        self._thread.start()

        deadline = time.time() + ENDPOINT_HANDSHAKE_TIMEOUT
        while time.time() < deadline:
            if self._post_url:
                return
            if not self._thread.is_alive():
                raise RuntimeError("SSE 读取线程提前退出")
            time.sleep(0.05)

        try:
            resp.close()
        except Exception:
            pass
        self._response = None
        raise RuntimeError("未能在 SSE 流中找到 endpoint 事件")

    def close(self) -> None:
        self._closed = True
        if self._response is not None:
            try:
                self._response.close()
            except Exception:
                pass
        # 唤醒所有 pending
        with self._lock:
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(RuntimeError("client closed"))
            self._pending.clear()

    # ---- 后台读 SSE ----

    def _reader_loop(self) -> None:
        """持续读 SSE 事件，按 `id` 把响应喂回对应的 Future。
        同时把 `endpoint` 事件的 data 解析为 POST URL（支持相对路径）。

        容错点：某些 MCP server（如 ModelScope）的实现把 `event:` 和 `data:`
        分到两个独立的"事件块"里发送，块间空行分隔。标准 SSE 不允许这种跨块
        配对，但实际 server 普遍存在。我们只在"真正 dispatch"时重置 evt_type，
        让下一个块继承上一个块的 event 标识。
        """
        evt_type: Optional[str] = None
        data_parts: List[str] = []
        try:
            assert self._response is not None
            for raw in self._response.iter_lines(chunk_size=1, decode_unicode=True):
                if raw is None:
                    continue
                line = raw.rstrip("\r")
                if line == "":
                    if data_parts:
                        payload = "\n".join(data_parts)
                        evt = evt_type or "message"
                        self._handle_event(evt, payload)
                        # 只有真正 dispatch 才重置 evt_type
                        evt_type = None
                        data_parts = []
                    # 否则：保留 evt_type 给下一个 data 块（容错非标准 SSE）
                elif line.startswith("event:"):
                    evt_type = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    data_parts.append(line.split(":", 1)[1].lstrip())
                elif line.startswith(":"):
                    # SSE 注释，跳过
                    pass
                # 其余字段（id:, retry:）忽略
        except Exception as e:  # noqa: BLE001
            # 区分"正常 idle 超时"vs"真异常"：如果 endpoint 已拿到（POST 可用），
            # 说明握手成功，reader 后续 hang 等 message 属正常路径，不打 warning。
            if self._post_url:
                logger.debug("[mcp:%s] SSE reader 退出（已拿到 endpoint，正常）：%s", self.server_name, e)
            else:
                logger.warning("[mcp:%s] SSE 流异常：%s", self.server_name, e)
            with self._lock:
                for fut in self._pending.values():
                    if not fut.done():
                        fut.set_exception(RuntimeError(f"SSE 流断开：{e}"))
                self._pending.clear()

    def _handle_event(self, event_type: str, data: str) -> None:
        # endpoint 事件：解析 POST URL（可能是相对路径）
        if event_type == "endpoint" and not self._post_url:
            raw_url = data.strip()
            absolute = raw_url if raw_url.startswith(("http://", "https://")) else urljoin(self.url, raw_url)
            with self._lock:
                self._post_url = absolute
            return
        # 其余事件走原派发
        self._dispatch(event_type, data)

    def _absolute_post_url(self) -> Optional[str]:
        """确保 POST URL 是绝对路径。"""
        pu = self._post_url
        if not pu:
            return None
        if pu.startswith(("http://", "https://")):
            return pu
        return urljoin(self.url, pu)

    def _dispatch(self, event_type: str, data: str) -> None:
        self._last_event_ts = time.time()
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            logger.warning("[mcp:%s] 非 JSON 事件：%r", self.server_name, data[:80])
            return
        if not isinstance(payload, dict):
            return
        req_id = payload.get("id")
        if req_id is None:
            # 通知类消息，无 id
            return
        key = str(req_id)
        with self._lock:
            fut = self._pending.pop(key, None)
        if fut is not None and not fut.done():
            fut.set_result(payload)

    # ---- 发送 JSON-RPC ----

    def _send_request(self, method: str, params: Optional[Dict[str, Any]] = None,
                      timeout: float = REQUEST_TIMEOUT) -> Dict[str, Any]:
        req_id = uuid.uuid4().hex
        body: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
        }
        if params is not None:
            body["params"] = params

        # HTTP 模式：单次 POST 直接拿响应（更快，无需 SSE 长连接）
        if self._mode == "http":
            return self._http_post(body, timeout=timeout)

        # SSE 模式：POST 到 endpoint，等 reader 喂回响应
        fut: Future = Future()
        with self._lock:
            self._pending[req_id] = fut

        post_url = self._absolute_post_url()
        if not post_url:
            with self._lock:
                self._pending.pop(req_id, None)
            return {"error": "未连接到 MCP server（post_url 为空）"}

        try:
            r = requests.post(
                post_url,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                data=json.dumps(body, ensure_ascii=False),
                timeout=10,
            )
            if r.status_code >= 400:
                with self._lock:
                    self._pending.pop(req_id, None)
                return {"error": f"POST 失败 HTTP {r.status_code}: {r.text[:120]}"}
        except requests.RequestException as e:
            with self._lock:
                self._pending.pop(req_id, None)
            return {"error": f"POST 异常：{e}"}

        try:
            payload = fut.result(timeout=timeout)
        except FutTimeoutError:
            with self._lock:
                self._pending.pop(req_id, None)
            return {"error": f"等待响应超时（{timeout}s）"}
        except Exception as e:  # noqa: BLE001
            return {"error": f"等待响应异常：{e}"}

        if "error" in payload:
            err = payload["error"]
            return {"error": f"MCP 返回错误：{err.get('message', err)}", "code": err.get("code")}
        return payload.get("result", {})

    def _http_post(self, body: Dict[str, Any], timeout: float = REQUEST_TIMEOUT) -> Dict[str, Any]:
        """Streamable HTTP 单次请求：直接 POST 拿响应。"""
        if not self._http_url:
            return {"error": "HTTP 模式未初始化"}
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        try:
            r = requests.post(
                self._http_url,
                headers=headers,
                data=json.dumps(body, ensure_ascii=False),
                timeout=timeout,
            )
        except requests.RequestException as e:
            return {"error": f"POST 异常：{e}"}
        if r.status_code == 404 and self._session_id:
            # session 可能过期，丢弃 session 让上层重新 initialize
            logger.info("[mcp:%s] session 过期（404），清除", self.server_name)
            self._session_id = None
        if r.status_code >= 400:
            return {"error": f"POST 失败 HTTP {r.status_code}: {r.text[:120]}"}
        # 响应可能是 JSON 也可能是 SSE 流（Content-Type: text/event-stream）
        ctype = (r.headers.get("Content-Type") or "").lower()
        if "text/event-stream" in ctype:
            # 单次 SSE 响应：从流里解析第一个 event/message 的 data 即可
            try:
                text = r.text
            except Exception as e:
                return {"error": f"读 SSE 响应失败：{e}"}
            return self._parse_sse_response(text)
        try:
            payload = r.json()
        except ValueError:
            return {"error": f"响应非 JSON：{r.text[:120]}"}
        if isinstance(payload, dict) and "error" in payload:
            err = payload["error"]
            return {"error": f"MCP 返回错误：{err.get('message', err)}", "code": err.get("code")}
        return payload.get("result", {}) if isinstance(payload, dict) else {}

    @staticmethod
    def _parse_sse_response(text: str) -> Dict[str, Any]:
        """从单次 SSE 响应文本中提取第一个 event/message 的 JSON。"""
        evt_type: Optional[str] = None
        data_parts: List[str] = []
        for raw in text.splitlines():
            line = raw.rstrip("\r")
            if line == "":
                if data_parts:
                    payload = "\n".join(data_parts)
                    try:
                        return json.loads(payload)
                    except json.JSONDecodeError:
                        return {"error": f"响应非 JSON：{payload[:120]}"}
                evt_type = None
                data_parts = []
            elif line.startswith("event:"):
                evt_type = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_parts.append(line.split(":", 1)[1].lstrip())
        return {"error": "SSE 响应无有效数据"}

    def _send_notification(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        body: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            body["params"] = params

        if self._mode == "http":
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            }
            if self._session_id:
                headers["Mcp-Session-Id"] = self._session_id
            try:
                requests.post(
                    self._http_url or "", headers=headers,
                    data=json.dumps(body, ensure_ascii=False), timeout=4,
                )
            except requests.RequestException:
                pass
            return

        post_url = self._absolute_post_url()
        if not post_url:
            return
        try:
            requests.post(
                post_url,
                headers={"Content-Type": "application/json"},
                data=json.dumps(body, ensure_ascii=False),
                timeout=5,
            )
        except requests.RequestException:
            pass

    # ---- 业务接口 ----

    def initialize(self) -> Dict[str, Any]:
        if self._initialized:
            return {}
        result = self._send_request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": CLIENT_INFO,
        })
        if "error" not in result:
            self._send_notification("notifications/initialized")
            self._initialized = True
        return result

    def list_tools(self) -> List[Dict[str, Any]]:
        init = self.initialize()
        if "error" in init:
            return []
        result = self._send_request("tools/list")
        if isinstance(result, dict) and "error" in result:
            return []
        tools = result.get("tools") if isinstance(result, dict) else None
        if not isinstance(tools, list):
            return []
        # 转成 OpenAI function-calling schema
        out: List[Dict[str, Any]] = []
        for t in tools:
            if not isinstance(t, dict):
                continue
            name = t.get("name")
            if not name:
                continue
            schema = t.get("inputSchema") or {"type": "object", "properties": {}}
            out.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": t.get("description") or "",
                    "parameters": schema,
                },
            })
        return out

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        init = self.initialize()
        if "error" in init:
            return {"error": init["error"], "server": self.server_name, "tool": name}
        result = self._send_request(
            "tools/call",
            {"name": name, "arguments": arguments or {}},
            timeout=CALL_TOOL_TIMEOUT,
        )
        if isinstance(result, dict) and "error" in result:
            return {"error": result["error"], "server": self.server_name, "tool": name}
        # MCP 标准返回: {"content": [{"type": "text", "text": "..."}], "isError": bool}
        # 把 content 数组的第一个 text 元素尝试 JSON 解析，否则原样返回
        content = result.get("content") if isinstance(result, dict) else None
        text_blob = ""
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict):
                text_blob = first.get("text", "") or ""
        parsed: Any = text_blob
        if text_blob:
            try:
                parsed = json.loads(text_blob)
            except json.JSONDecodeError:
                parsed = text_blob
        return {
            "content": parsed,
            "isError": bool(result.get("isError")) if isinstance(result, dict) else False,
            "server": self.server_name,
            "tool": name,
            "raw": result,
        }


# ---------------- 模块缓存 ----------------

_CLIENT_CACHE: Dict[str, McpSseClient] = {}
_CLIENT_LOCK = threading.Lock()


def _get_or_create(server_name: str, url: str) -> McpSseClient:
    with _CLIENT_LOCK:
        cli = _CLIENT_CACHE.get(server_name)
        if cli is not None and cli.url == url and not cli._closed:
            return cli
        if cli is not None:
            try:
                cli.close()
            except Exception:
                pass
            _CLIENT_CACHE.pop(server_name, None)
        cli = McpSseClient(server_name, url)
        _CLIENT_CACHE[server_name] = cli
        return cli


def _evict(server_name: str) -> None:
    with _CLIENT_LOCK:
        cli = _CLIENT_CACHE.pop(server_name, None)
    if cli is not None:
        try:
            cli.close()
        except Exception:
            pass


# ---------------- 业务函数 ----------------

def load_mcp_tools() -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """从 config 读取 enabled server，并发/顺序地 list_tools，返回:
    - 工具列表（已加 {server_name}__ 前缀）
    - 工具名 → server_name 反向映射
    """
    cfg = load_config()
    servers = ((cfg.get("mcp") or {}).get("servers") or [])
    out_tools: List[Dict[str, Any]] = []
    out_map: Dict[str, str] = {}

    for srv in servers:
        if not isinstance(srv, dict):
            continue
        if not srv.get("enabled"):
            continue
        name = (srv.get("name") or "").strip()
        url = (srv.get("url") or "").strip()
        if not name or not url:
            continue

        cli = _get_or_create(name, url)
        try:
            cli.connect()
        except Exception as e:  # noqa: BLE001
            logger.warning("[mcp] %s 连接失败：%s", name, e)
            _evict(name)
            continue

        try:
            raw_tools = cli.list_tools()
        except Exception as e:  # noqa: BLE001
            logger.warning("[mcp] %s list_tools 失败：%s", name, e)
            _evict(name)
            continue

        if not raw_tools:
            # initialize 失败 / tools 为空
            continue

        for t in raw_tools:
            try:
                fn = t["function"]
                original_name = fn["name"]
            except (KeyError, TypeError):
                continue
            prefixed = f"{name}__{original_name}"
            # 不修改原 dict 的 description 加后缀，便于 LLM 知道工具来源
            desc = fn.get("description") or ""
            if "[来自" not in desc:
                fn["description"] = f"[来自 {name} MCP] {desc}".strip()
            fn["name"] = prefixed
            out_tools.append(t)
            out_map[prefixed] = name

    return out_tools, out_map


def call_mcp_tool(prefixed_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """按 `__` 拆分前缀名，路由到对应 server 的 McpSseClient。"""
    if "__" not in prefixed_name:
        return {"error": f"MCP 工具名格式错误（需包含 __）：{prefixed_name}"}
    server_name, tool_name = prefixed_name.split("__", 1)

    cfg = load_config()
    servers = ((cfg.get("mcp") or {}).get("servers") or [])
    url = ""
    for srv in servers:
        if isinstance(srv, dict) and (srv.get("name") or "").strip() == server_name:
            url = (srv.get("url") or "").strip()
            break

    if not url:
        return {"error": f"未找到 MCP server 配置：{server_name}", "server": server_name, "tool": tool_name}

    cli = _get_or_create(server_name, url)
    try:
        cli.connect()
    except Exception as e:  # noqa: BLE001
        _evict(server_name)
        return {"error": f"连接 {server_name} MCP 失败：{e}", "server": server_name, "tool": tool_name}

    return cli.call_tool(tool_name, arguments or {})


def test_server(name: str, url: str) -> Dict[str, Any]:
    """单条 MCP server 连接测试：建临时客户端，list_tools 后立即关闭。"""
    if not name or not url:
        return {"ok": False, "message": "name 与 url 均不能为空"}
    cli = McpSseClient(name.strip(), url.strip())
    try:
        cli.connect()
    except Exception as e:  # noqa: BLE001
        try:
            cli.close()
        except Exception:
            pass
        return {"ok": False, "message": f"连接失败：{e}"}

    try:
        tools = cli.list_tools()
    except Exception as e:  # noqa: BLE001
        try:
            cli.close()
        except Exception:
            pass
        return {"ok": False, "message": f"列出工具失败：{e}"}

    try:
        cli.close()
    except Exception:
        pass

    names = [t["function"]["name"] for t in tools if isinstance(t.get("function"), dict)]
    if not names:
        return {"ok": True, "message": "连接成功，但 server 未声明任何工具", "tools": []}
    preview = ", ".join(names[:5])
    suffix = " 等" if len(names) > 5 else ""
    return {
        "ok": True,
        "message": f"成功，{len(names)} 个工具：{preview}{suffix}",
        "tools": names,
    }