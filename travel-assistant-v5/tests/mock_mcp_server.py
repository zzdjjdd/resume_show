"""本地 Mock MCP Server(仅用于测试)。

实现标准 MCP 协议(JSON-RPC 2.0 over HTTP),暴露 2 个工具:
- get_weather(city): 模拟天气
- search_train(from, to, date): 模拟火车票查询

启动:python -m tests.mock_mcp_server  (端口 18765)
"""
import json
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

TOOLS = [
    {
        "name": "get_weather",
        "description": "查询指定城市的天气",
        "inputSchema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "城市名,如 北京 / 上海"}
            },
            "required": ["city"]
        }
    },
    {
        "name": "search_train",
        "description": "查询两城之间的高铁/动车票",
        "inputSchema": {
            "type": "object",
            "properties": {
                "from_city": {"type": "string"},
                "to_city": {"type": "string"},
                "date": {"type": "string", "description": "YYYY-MM-DD"}
            },
            "required": ["from_city", "to_city", "date"]
        }
    },
]


def _make_result(content_items):
    return {"content": [{"type": "text", "text": json.dumps(item, ensure_ascii=False)} for item in content_items]}


def _handle_tools_list():
    return {"tools": TOOLS}


def _handle_tools_call(name, args):
    if name == "get_weather":
        city = args.get("city", "北京")
        return _make_result([{
            "city": city,
            "weather": "晴",
            "temperature": 26,
            "humidity": 45,
        }])
    if name == "search_train":
        return _make_result([{
            "from": args.get("from_city"),
            "to": args.get("to_city"),
            "date": args.get("date"),
            "trains": [
                {"no": "G101", "depart": "07:00", "arrive": "11:30", "duration": "4h30m", "price": 553},
                {"no": "G3",   "depart": "09:00", "arrive": "13:28", "duration": "4h28m", "price": 553},
                {"no": "G7",   "depart": "11:00", "arrive": "15:30", "duration": "4h30m", "price": 553},
            ]
        }])
    return {"isError": True, "content": [{"type": "text", "text": f"未知工具: {name}"}]}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args, **kwargs):
        pass  # 静音

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            req = json.loads(raw)
        except Exception:
            return self._reply({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}, status=400)

        method = req.get("method")
        req_id = req.get("id")
        params = req.get("params") or {}

        # 返回 session id
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("mcp-session-id", "mock-session-" + uuid.uuid4().hex[:8])
        self.end_headers()

        if method == "initialize":
            body = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "mock-mcp", "version": "1.0.0"}
                }
            }
        elif method == "notifications/initialized":
            return  # 204
        elif method == "tools/list":
            body = {"jsonrpc": "2.0", "id": req_id, "result": _handle_tools_list()}
        elif method == "tools/call":
            try:
                body = {"jsonrpc": "2.0", "id": req_id, "result": _handle_tools_call(params.get("name"), params.get("arguments", {}))}
            except Exception as e:
                body = {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32603, "message": str(e)}}
        else:
            body = {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}

        self.wfile.write(json.dumps(body, ensure_ascii=False).encode("utf-8"))


class ThreadingServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


if __name__ == "__main__":
    port = 18765
    print(f"[mock-mcp] listening on http://127.0.0.1:{port}")
    ThreadingServer(("127.0.0.1", port), Handler).serve_forever()
