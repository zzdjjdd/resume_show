---
paths:
  - "backend/mcp_client.py"
  - "backend/ai_service.py"
  - "backend/config.py"
---

# 04 · MCP 规则（外部 MCP-over-SSE 接入）

仅聊天模式（`chat_stream`）暴露 MCP；旅游流程不调 LLM tools，不暴露 MCP。

## 工具命名空间

外部 MCP server 的工具名形如 `{server_name}__{tool_name}`，避免与 amap 工具或
不同 server 之间命名冲突。分发时按 `__` 拆分，前缀由 `mcp_client.load_mcp_tools()` 自动加：

```python
if "__" in name:
    server_name, tool_name = name.split("__", 1)
    result = mcp_client.call_mcp_tool(name, args)  # 内部按 __ 拆
```

## 新增外部 MCP 工具：无需改 Python

工具列表由 MCP server 在握手时自报（`tools/list`），由 `mcp_client.load_mcp_tools()`
自动加前缀注入。`_summarize_tool_result` 的 `__` 兜底分支已覆盖通用情况。

> 只有当 server 名字固定、且你想给它做更精确的中文摘要时，才需要在
> `_summarize_tool_result` 里加 `name.startswith("xxx__")` 分支。
> **不要**手动往 `amap_service.MCP_TOOLS` 或 `_summarize_tool_result` 里加 MCP 工具。

## 长连接缓存（关键约束）

`mcp_client._CLIENT_CACHE` 按 `server.name` 复用 SSE 长连接；同一 server 多次
`tools/call` 只握手一次。

- **不要**改成短连接（每次 call 重连会慢得多）。
- **不要**在 `chat_stream` 退出时主动 close——下次请求复用。

## 协议握手（backend/mcp_client.py）

1. `GET <url>` 带 `Accept: text/event-stream` → 服务端持续推 SSE 事件。
2. 第一个事件为 `event: endpoint`，`data:` 字段为 POST URL；客户端记下。
3. 客户端 `POST <endpoint>` 发送 JSON-RPC 2.0 请求：
   - `initialize` → `notifications/initialized`（无 id 无响应） → `tools/list` → 拿 tools。
   - `tools/call` → 拿 `{"content": [{"type": "text", "text": "..."}], "isError": false}`。
4. 服务端用 `event: message` + `data: <jsonrpc-response>` 回送响应，客户端按 `id` 回调。

## 错误策略

上游不可达 / `tools/list` 失败 → 跳过该 server 的工具注入，**不抛异常、不打断对话**；
聊天流继续走 amap 工具。设置页「测试连接」单独走 `test_server()` 把错误回显给用户。

## 模块边界

`mcp_client.py` 是**唯一**允许直连外部 MCP upstream SSE 的模块。
导出 `load_mcp_tools() / call_mcp_tool() / test_server()` 三个纯函数。

## SSE 事件兼容

`tool` 事件 payload 新增 `server` 字段，未启用 MCP 时为 `null`。
其他事件类型与字段不变，向后兼容。
