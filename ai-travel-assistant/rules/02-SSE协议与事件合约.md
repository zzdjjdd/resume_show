---
paths:
  - "backend/ai_service.py"
  - "backend/main.py"
  - "frontend/js/**"
---

# 02 · SSE 协议与事件合约（核心合约）

`/api/travel/plan` 与 `/api/chat` 都是 `text/event-stream`，遵循同一套协议。

## 帧格式

每帧：

```
data: { "type": "<event>", ... }\n\n
```

终止帧固定为：

```
data: [DONE]\n\n
```

## `/api/chat` 事件类型

| `type` | 字段 | 含义 |
|---|---|---|
| `thinking` | `content` | LLM 的 `reasoning_details`（思考过程），增量 |
| `delta` | `content` | LLM 自然语言回复的 token 增量 |
| `step` | `phase, step, title, icon, content?, summary?, data?, decision?, status?` | ReAct 阶段事件 |
| `tool` | `name, server?, args, result` | 一次工具调用的输入与输出（带可读摘要） |
| `error` | `message` | 中断错误，前端展示红条 |
| `done` | — | 流结束（紧跟 [DONE] 之前还会有一帧 `tools` 汇总） |

- ReAct 的 `step ∈ {thought, intent, tool_select, args, action, observation, iterate}`。
- `phase ∈ {begin, delta, end}`：前端按 `phase=begin` 起折叠面板，`delta` 累加内容，`end` 收尾。
- **`tool` 事件的 `server` 字段**：本地 amap 工具为 `null`；外部 MCP 工具为 server name（前端展示「🔌 来自 xxx MCP」）。**不要**从 payload 里去掉。

## `/api/travel/plan` 事件类型

| `type` | 含义 |
|---|---|
| `step` | 旅游进度步骤，`step ∈ {prepare, geocode, route, weather, ai, integrate}` |
| `delta` | AI 撰写 Markdown 的 token 增量 |
| `result` | 最终结果：`ok, markdown, enrichments, message?` |
| `error` / `done` | 同上 |

## 固定步骤名（改名前先改代码）

- 聊天 ReAct：`thought / intent / tool_select / args / action / observation / iterate`
- 旅游模式：`prepare / geocode / route / weather / ai / integrate`

改名前先在 `ai_service.py` 顶部的 `STEP_META` / `TRAVEL_STEPS` 一并改。

## reasoning_split

调用 LLM 时附带 `extra_body={"reasoning_split": True}`，服务端把思考过程放到
`choices[0].message.reasoning_details`，前端用 `thinking` 事件呈现。
`config.json` 中 `llm.reasoning_split` 可关。

## 改动即合约

> 任何流式响应的 **yield 顺序** 与 **事件类型集合** 都是前端合约。
> 改动前先在 `frontend/js/app.js` 搜索 `event.type` / `case 'step'`，
> 同步更新对应 `case` 分支，否则前端会**静默丢失数据**。
