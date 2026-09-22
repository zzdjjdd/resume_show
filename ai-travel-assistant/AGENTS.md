# AGENTS.md

给所有 AI 编码代理（Cline、Cursor、Aider、本地 Codex、Claude Code……）共同遵守的项目说明。
把它当成一份**项目档案**：架构、API 合约、SSE 事件协议、扩展指引、开发工作流。

---

## 1. 项目目标

**AI 智行助手** —— 一个单机演示级的智能出行助手，面向「端云协同」主题：

- 让用户在前端页面配好**任意 OpenAI 兼容 LLM** 与**高德地图**凭据后，即可使用：
  - **旅游模式**：表单一次性生成 Markdown 行程计划，可下载 / 复制。
  - **日常聊天**：多轮对话 + 自动调用地图工具（天气、POI、路线、距离……）。
- 代码刻意保持小而清晰，方便作为教学 / demo 二次修改。

非目标（明确不做）：

- 多用户、鉴权、生产部署、TLS、CORS 收紧。
- 引入前端框架或构建步骤。
- 替换 FastAPI / 替换 SQLite 等基础设施改动。

---

## 2. 技术栈

| 层 | 选型 | 版本（见 requirements.txt） |
|---|---|---|
| 后端框架 | FastAPI | 0.110.0 |
| ASGI | uvicorn[standard] | 0.27.1 |
| LLM SDK | openai（兼容任意 OpenAI 兼容端点） | 1.13.3 |
| HTTP 客户端 | requests / httpx（前者用于高德，后者被 openai SDK 用） | — |
| 校验 | pydantic | 2.6.3 |
| 表单 | python-multipart | 0.0.9 |
| 前端 | 原生 HTML / CSS / JS，marked.js 12.0.2（CDN） | — |
| 运行时 | Python ≥ 3.10 | — |

LLM 默认：`MiniMax-M3`，base_url 默认 `https://api.minimaxi.com/v1`。`config.json` 里可改任意 OpenAI 兼容服务。

---

## 3. 目录结构与职责

```
demo/
├── start.bat                 # Windows 一键启动（pip install + uvicorn）
├── backend/
│   ├── __init__.py           # 标识 backend 为包，让 main.py 用 `from . import ...`
│   ├── main.py               # FastAPI app、CORS、所有 /api/* 路由、静态文件托管
│   ├── ai_service.py         # LLM 调用层（chat_stream、generate_travel_plan_stream、test_*）
│   ├── amap_service.py       # 高德开放平台 REST 封装 + MCP_TOOLS（工具 schema 表）
│   ├── mcp_client.py         # 通用 MCP-over-SSE 客户端（JSON-RPC + 长连接 Future 回调 + 缓存）
│   ├── config.py             # 读 / 写 / merge backend/config.json
│   ├── config.json           # 运行时配置 ⚠ 含 API Key
│   └── requirements.txt
└── frontend/
    ├── index.html            # 单页应用骨架（旅游 / 聊天 / 设置 三 Tab）
    ├── css/styles.css        # 玻璃拟态 UI、暗色 aurora 背景
    ├── js/app.js             # 表单提交、SSE 消费、Markdown 渲染、ReAct 步骤面板
    └── assets/               # （预留图标 / 图片）
```

**职责切分**：

- `main.py`：HTTP 边缘，只做参数校验、调用 ai_service、把生成器包成 `StreamingResponse`，**不要**在这里写业务逻辑。
- `ai_service.py`：唯一允许调用 OpenAI SDK / 编排 ReAct 循环的模块。所有 LLM 相关约定（事件、step 名、prompt、extra_body）都在这里定义。
- `amap_service.py`：纯函数式封装，唯一允许 `import requests` 去打高德 REST 的模块。`MCP_TOOLS` 是给 OpenAI `tools=` 参数用的 JSON Schema 列表。
- `mcp_client.py`：**唯一**允许直连外部 MCP upstream SSE 的模块。手写 JSON-RPC 2.0 over SSE 解析（`requests` 流式 GET + 后台线程读 SSE + `concurrent.futures.Future` 按 `id` 回调）。模块顶层 `_CLIENT_CACHE` 按 `server.name` 复用长连接，避免每个 tool call 重连。导出 `load_mcp_tools() / call_mcp_tool() / test_server()` 三个纯函数。
- `config.py`：配置 IO，唯一允许写 `config.json` 的地方。

---

## 4. API 合约（HTTP）

后端绑定 `0.0.0.0:8000`，CORS `*`。所有 `/api/*` 路径如下：

| 方法 | 路径 | 入参 | 出参 | 说明 |
|---|---|---|---|---|
| GET | `/api/config` | — | 整个 `config.json` | 前端回填表单用 |
| POST | `/api/config` | `{section: "llm"\|"amap", payload: {...}}` | `{ok, config}` | 局部更新一个 section |
| POST | `/api/test/llm` | — | `{ok, message, model?}` | 用 `max_tokens=1` 探活 |
| POST | `/api/test/amap` | — | `{ok, message}` | 调用 geocode("北京天安门") |
| POST | `/api/test/mcp` | `{name, url}` | `{ok, message, tools?}` | 单条 MCP server 连接 + 工具列表摘要 |
| POST | `/api/travel/plan` | `TravelRequest` | **SSE** | 行程生成 |
| POST | `/api/chat` | `{messages: [{role, content, ...}]}` | **SSE** | 聊天 + 工具调用 |

### 4.1 `TravelRequest`

```json
{
  "origin": "string",
  "destination": "string",
  "days": 1,
  "people": 2,
  "preferences": ["人文历史", "美食体验", "..."],
  "extra": "string",
  "use_map": false
}
```

### 4.2 `ChatMessage`

```json
{ "role": "user|assistant|system|tool",
  "content": "string",
  "tool_calls": [{"id","type":"function","function":{"name","arguments"}}],
  "tool_call_id": "string" }
```

---

## 5. SSE 事件协议（核心合约）

两个流式接口都遵循同一套协议。每一帧：

```
data: { "type": "<event>", ... }\n\n
```

终止帧固定为 `data: [DONE]\n\n`。

### 5.1 `/api/chat` 事件类型

| `type` | 字段 | 含义 |
|---|---|---|
| `thinking` | `content` | LLM 的 `reasoning_details`（思考过程），增量 |
| `delta` | `content` | LLM 自然语言回复的 token 增量 |
| `step` | `phase, step, title, icon, content?, summary?, data?, decision?, status?` | ReAct 阶段事件 |
| `tool` | `name, server?, args, result` | 一次工具调用的输入与输出（带可读摘要）。`server` 字段：本地 amap 工具为 `null`；外部 MCP 工具为 server name（前端展示「🔌 来自 xxx MCP」） |
| `error` | `message` | 中断错误，前端展示红条 |
| `done` | — | 流结束（紧跟 [DONE] 之前还会有一帧 `tools` 汇总） |

ReAct 的 `step ∈ {thought, intent, tool_select, args, action, observation, iterate}`，`phase ∈ {begin, delta, end}`。前端按 `phase=begin` 起一个折叠面板，`delta` 累加内容，`end` 收尾。

### 5.2 `/api/travel/plan` 事件类型

| `type` | 含义 |
|---|---|
| `step` | 旅游进度步骤，`step ∈ {prepare, geocode, route, weather, ai, integrate}` |
| `delta` | AI 撰写 Markdown 的 token 增量 |
| `result` | 最终结果：`ok, markdown, enrichments, message?` |
| `error` / `done` | 同上 |

> 任何代理改动 SSE 之前，必须在 `frontend/js/app.js` 同步更新对应 `case` 分支，否则前端会静默丢失数据。

---

## 6. 高德 MCP 工具表（`amap_service.MCP_TOOLS`）

`amap_service.py` 中以 OpenAI function-calling JSON Schema 形式暴露给 LLM：

| 工具名 | 高德接口 | 用途 |
|---|---|---|
| `amap_geocode` | `/v3/geocode/geo` | 地址 → 经纬度 |
| `amap_regeocode` | `/v3/geocode/regeo` | 经纬度 → 地址 |
| `amap_weather` | `/v3/weather/weatherInfo` | 实况 / 预报天气 |
| `amap_text_search` | `/v3/place/text` | 关键词搜 POI |
| `amap_around_search` | `/v3/place/around` | 周边搜 POI |
| `amap_route_driving` | `/v3/direction/driving` | 驾车路径 |
| `amap_route_walking` | `/v3/direction/walking` | 步行路径 |
| `amap_route_transit` | `/v3/direction/transit/integrated` | 公交路径 |
| `amap_route_bicycling` | `/v3/direction/bicycling` | 骑行路径 |
| `amap_distance` | `/v3/distance` | 直线 / 通行距离 |

> **新增工具**的三处必改清单：`amap_service.py`（实现 + 加入 `MCP_TOOLS`）、`ai_service.py` 的 `_summarize_tool_result`（中文摘要分支）、如有新参数类型则在 `TravelRequest` / `ChatMessage` 上扩展。**不**要在 `main.py` 里写工具逻辑。

### 6.1 外部 MCP Server 接入（聊天模式）

允许用户在前端「设置」添加**任意** MCP-over-SSE server，LLM 自动发现其工具并调用。

**配置结构**（`config.mcp.servers` 数组，每条 `{name, url, enabled}`）：

```json
{
  "mcp": {
    "servers": [
      { "name": "12306", "url": "https://.../sse", "enabled": true },
      { "name": "hotel",  "url": "https://.../sse", "enabled": true }
    ]
  }
}
```

默认占位 12306（火车票）与酒店（搜索与推荐）两条；URL 留空表示未启用。**任意多个** server 并存，列表动态增删。

**工具命名空间**：所有外部 MCP 工具在 LLM 看来是 `{server_name}__{tool_name}`，避免与 amap 工具或不同 server 之间的命名冲突。分发时按 `__` 拆分：

```python
if "__" in name:
    server_name, tool_name = name.split("__", 1)
    result = mcp_client.call_mcp_tool(name, args)  # 内部按 __ 拆
```

**协议握手**（`backend/mcp_client.py` 实现）：

1. `GET <url>` 带 `Accept: text/event-stream` → 服务端持续推 SSE 事件。
2. 第一个事件为 `event: endpoint`，`data:` 字段为 POST URL；客户端记下。
3. 客户端 `POST <endpoint>` 发送 JSON-RPC 2.0 请求：
   - `initialize` → `notifications/initialized`（无 id 无响应） → `tools/list` → 拿 tools。
   - `tools/call` → 拿 `{"content": [{"type": "text", "text": "..."}], "isError": false}`。
4. 服务端用 `event: message` + `data: <jsonrpc-response>` 回送响应，客户端按 `id` 回调。

**错误策略**：上游不可达 / `tools/list` 失败 → 跳过该 server 的工具注入，**不抛异常、不打断对话**；聊天流继续走 amap 工具。设置页「测试连接」单独走 `test_server()` 把错误回显给用户。

**缓存策略**：`_CLIENT_CACHE` 按 `server.name` 复用 SSE 长连接；同一 server 多次 `tools/call` 只握手一次。**不要**改成短连接（每次 call 重连会慢得多）；**不要**在 `chat_stream` 退出时主动 close——下次请求复用。

**暴露范围**：仅聊天模式（`chat_stream`）。旅游流程（`generate_travel_plan_stream`）不调 LLM tools，不暴露 MCP。

**SSE 事件协议兼容**：`tool` 事件 payload 新增 `server` 字段，未启用 MCP 时为 `null`。其他事件类型与字段不变，向后兼容。

---

## 7. 配置 `config.json` 结构

```json
{
  "llm": {
    "api_key": "sk-... | <空>",
    "base_url": "https://... | <空>",
    "model": "MiniMax-M3",
    "reasoning_split": true
  },
  "amap": {
    "sse_url": "<高德 MCP 上游 SSE URL，未启用>",
    "api_key": "<高德开放平台 Web 服务 Key>"
  }
}
```

- **空 `api_key` + 空 `base_url`** → `OpenAI()` 不带参数，读环境变量（`OPENAI_API_KEY` / `OPENAI_BASE_URL`）。
- `reasoning_split=true` → 调 LLM 时附带 `extra_body={"reasoning_split": True}`，让 `choices[0].message.reasoning_details` 承载思考链。
- `config.json` 由前端设置页写入，**仅本机使用**；如要纳入 git，必须忽略真实凭据文件并以 `config.example.json` 提供模板。

```json
{
  "llm":  { "api_key": "sk-...", "base_url": "https://...", "model": "MiniMax-M3", "reasoning_split": true },
  "amap": { "sse_url": "https://mcp.../sse", "api_key": "高德 Web 服务 Key" },
  "mcp":  {
    "servers": [
      { "name": "12306", "url": "https://.../sse", "enabled": true },
      { "name": "hotel",  "url": "https://.../sse", "enabled": true }
    ]
  }
}
```

---

## 8. 开发工作流

### 8.1 本地启动

```
# Windows
start.bat

# 任意平台
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --app-dir .
```

打开 `http://localhost:8000/` → 「设置」Tab 填凭据 → 「测试连接」。

### 8.2 修改规范

1. **改业务前**先读 `backend/ai_service.py` 顶部 80 行的模块注释，记住事件协议。
2. **改前端前**先 grep `event.type` / `case 'step'` 看现有事件消费点。
3. 一次只动一个层级（后端 API / 前端消费 / LLM 行为），逐项验证。
4. 提交前确认 `backend/config.json` 没被改动（用户数据，不应入库）。

### 8.3 手工验收清单

| # | 操作 | 期望 |
|---|---|---|
| 1 | 启动服务并打开首页 | 三 Tab 可切换，无 console 报错 |
| 2 | 设置 → 填 LLM → 「测试连接」 | 弹 `连接成功（xx ms）` |
| 3 | 设置 → 填高德 → 「测试连接」 | 弹 `连接成功（示例解析到：北京天安门...）` |
| 4 | 旅游 → 北京→上海、3 天、勾「借助高德」→ 生成 | 6 个 step 依次出现，右侧渲染 Markdown |
| 5 | 聊天 → "上海今天天气怎么样？" | 出现 `tool` 事件 + 文字回答，天气含 `dayweather / daytemp` |
| 6 | 聊天 → "北京附近的咖啡馆" | 触发 `amap_around_search` |
| 7 | 聊天 → 连续工具调用超过 5 轮 | 第 6 轮不再发起工具调用 |
| 8 | 设置 → MCP 加一条 server（12306）→ 保存 → 启用 → 去 chat 问相关问题 | 聊天面板出现 `🔌 来自 12306 MCP` 标识；`tool` 事件 payload `server` 字段 = "12306" |
| 9 | 设置 → MCP 单条「测试」按钮 | 显示「成功，N 个工具：xxx, yyy, zzz」或具体失败原因 |
| 10 | 设置 → MCP 禁用某 server 后去 chat 提问 | LLM 不再列出该 server 的工具，工具调用 0 次 |
| 11 | 关闭所有 MCP server（仅 amap） | chat 流式事件序列与改造前**完全一致**（`tool` 事件 `server: null`） |

---

## 9. 已知坑位（改前必看）

| 现象 | 根因 | 处理 |
|---|---|---|
| `TypeError: Client.__init__() got an unexpected keyword argument 'proxies'` | openai 1.13.3 在内部给 httpx 0.28+ 传了已废弃的 `proxies=` | **不要**直接升 openai ≥ 1.20；用 `_build_http_client()` 显式 httpx.Client 绕过 |
| LLM 回复没有思考过程 | 没传 `reasoning_split` 或模型不支持 | `config.json` 留 `reasoning_split=true`，并在系统 prompt 里提示模型 |
| 高德调不到 | `amap.api_key` 为空 / Key 类型错 | 设置页填「Web 服务 JS API Key」而不是「Web 端 JS API Key」 |
| 前端 Markdown 不渲染 | marked.js CDN 被墙 | 改为本地 `frontend/assets/marked.min.js` 并改 `<script src>` |
| 工具循环死循环 | ReAct 没收敛 | `ai_service.chat_stream` 内置 5 轮硬上限，**不要**去掉 |
| MCP server 连不上 / endpoint 找不到 | URL 不是标准 MCP SSE；或 server 用其他协议（stdio / websocket） | 设置页「测试」按钮会给出原因；URL 写错也会立刻可看到。前端不会弹出红色错误（被吞掉走兜底） |
| MCP server 返回 200 但无 `endpoint` 事件 | 协议不一致（不是 JSON-RPC over SSE） | 当前 `_CLIENT_CACHE` 一次握手失败后会 evict；下次调用重新尝试。改进要扩 `McpSseClient` |
| MCP server 工具名不带 `__` 命名空间 | 未启用 MCP 或 server 未声明工具 | `_ensure_tools()` 只合并 enabled server；LLM 看不到工具列表 |
| 某些 MCP server 需要鉴权 header | 当前 `McpSseClient` 不支持自定义 header | 改 `mcp_client.McpSseClient.connect()` 加 `headers` 参数；同步更新 `ConfigSection` 与前端 UI |

---

## 10. 给代理的协作准则

- **不要重构为新框架**（如换 React / 换 Litestar / 加 ORM）。本项目的简洁性是 feature，不是 debt。
- **不要新增依赖**而不更新 `requirements.txt` 与本文件「技术栈」表格。
- **不要触碰 `config.json`** 当成代码——它是用户运行时数据。
- **新增事件类型**时，按本文件第 5 节的表格扩列，并在 `app.js` 加 `case` 分支，否则前端会丢消息。
- **回答用户问题时优先用中文**，与本项目 UI / prompt 风格一致。
- 一切对 LLM 输出格式的假设都要在 `ai_service.SYSTEM_PROMPT` 里有显式约束，**不要**靠猜。
- **"新增 MCP 工具"是 server 自报**，**不要**手动往 `amap_service.MCP_TOOLS` 或 `_summarize_tool_result` 里加 MCP 工具；它们由 `mcp_client.load_mcp_tools()` 自动注入，命名空间自动加 `{server_name}__` 前缀。
- 不要把 `mcp_client._CLIENT_CACHE` 改成短连接；不要在 `chat_stream` 退出时主动 close client。