# CLAUDE.md

给 Claude Code 的项目级指引（自动加载）。本文件只保留**每次会话都需要的入口与红线**；
详细内容已去重，分布在两处，不要在这里重复它们：

- **`AGENTS.md`** —— 唯一的完整项目档案：架构、API 合约、SSE 事件协议、MCP 接入、已知坑位。
- **`rules/`** —— 按主题拆分的任务级规则，每个文件头部 `paths:` 标明生效的文件范围。

> 冲突时以 `AGENTS.md` 为准；`rules/` 是它按主题 / 路径的归类整理。

## 项目一句话

**AI 智行助手**：FastAPI + 原生 HTML/CSS/JS 的单机演示应用。LLM（默认 MiniMax-M3，可换任意
OpenAI 兼容模型）+ 高德地图，两种模式——旅游模式一次性生成 Markdown 行程；聊天模式多轮对话 +
流式输出 + 自动工具调用（最多 **5 轮**）。

## 启动

```
start.bat            # Windows：pip install + uvicorn，端口 8000
# 或
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --app-dir .
```

前端 `http://localhost:8000/`，首次使用在「设置」页填 LLM / 高德凭据并「测试连接」。

## 改代码前（按顺序）

1. 涉及哪类改动，先读 `rules/` 里对应主题文件（SSE / 配置 / MCP / 硬约束……）。
2. 需要完整合约细节时读 `AGENTS.md`。
3. 改任何流式响应前，先在 `frontend/js/app.js` 搜 `event.type` / `case 'step'`——
   yield 顺序与事件类型集合是前端合约，改动会让前端静默丢数据。

## 红线（任何情况不要做）

- ❌ 提交 / 外传 `backend/config.json`（含明文 Key）；`.gitignore` 必须忽略它，入库只留 `config.py` 的 `DEFAULT_CONFIG`（空值）。
- ❌ 在日志或错误信息里打印 api_key 明文（`GET /api/config` 返回全量仅供前端回填表单）。
- ❌ 把 `mcp_client._CLIENT_CACHE` 改成短连接，或在 `chat_stream` 退出时主动 close——长连接要跨请求复用。
- ❌ 从 `tool` 事件 payload 去掉 `server` 字段——前端靠它展示「🔌 来自 xxx MCP」。
- ❌ 在前端引入 React / Vue / 任何构建步骤（刻意保持纯静态）。
- ❌ 把 CORS 收紧到非 `*` 而不同步改文档（全放行是演示有意为之）。
- ❌ 把 OpenAI SDK 升到 ≥ 1.20 而不先验证 `proxies=` 报错（现由 `_build_http_client` 显式 httpx.Client 绕过）。
- ❌ 去掉 `ai_service.chat_stream` 的 5 轮工具调用硬上限（防 ReAct 死循环）。
- ❌ 把 `config.json` 当代码改——默认值一律改 `config.py` 的 `DEFAULT_CONFIG`。
- ❌ 手动往 `amap_service.MCP_TOOLS` / `_summarize_tool_result` 加外部 MCP 工具（由 `mcp_client.load_mcp_tools()` 自动注入）。

## 验证

后端无单测，照 `rules/07-测试验证.md` 的手工清单逐项过。
