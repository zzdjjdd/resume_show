# AGENTS.md — 多 Agent / Subagent 协作规范

> 本文件描述在本项目上使用 Claude Code 的 Agent/Subagent 时,**角色定义、职责边界、协作协议与代码层 agent 约定**。阅读本文件前请先读 `CLAUDE.md`。

---

## 1. 适用范围

本项目是一份**单体应用**(FastAPI 后端 + 原生前端),**代码本身没有多 Agent 运行时**。但 Claude Code 在此项目上工作时会涉及两类 Agent:

1. **Claude Code 自身的 Subagent**(`general-purpose`、`Explore`、`Plan`、`statusline-setup` 等)— 由 Claude Code 调度,本文件定义它们在此项目上的角色与禁区。
2. **代码层面的 LLM Agent**(`backend/chat_agent.py` 的 `ChatAgent`)— 这是项目里**唯一在生产路径上跑的 agent**,任何改动都必须围绕它的现有契约。

---

## 2. 项目内置 Agent:`ChatAgent`

### 2.1 职责

`backend/chat_agent.py::ChatAgent` 是项目唯一的运行时 agent,负责:
- 把用户消息 + 历史 + 系统提示组装成 LLM 消息
- 在 `max_tool_rounds`(默认 4)内循环让 LLM 决定是否调用高德 MCP 工具
- 把每轮 LLM 响应里的**思考内容**、**工具调用**、**正文**分别提取并以流式事件 yield
- 维护工具调用结果并回灌给 LLM 形成多轮 tool-use 闭环

### 2.2 契约(任何人修改前必须先读)

| 项 | 现状 | 改动前要确认 |
| --- | --- | --- |
| 工具列表来源 | `self.amap.tools()`,仅当 `amap.api_key` 非空才注入 | 不要让工具为空时仍传 `tools=None` 之外的空数组,LLM 会困惑 |
| 思考内容抽取 | `extract_reasoning()` 同时支持 `reasoning_details` / `reasoning` / `reasoning_content` | 新增 LLM 厂商时,先扩展 `extract_reasoning()`,不要在调用处硬编码 |
| 最大工具轮次 | `max_tool_rounds = 4` | 改大值会放大延迟与 token 消耗,需评估 |
| 工具调用参数解析 | `json.loads` 失败时降级为空字典 | 保持降级语义,不要抛异常 |
| 流式事件 schema | `thinking` / `tool` / `content` / `done` | 不要新增事件类型而不同步修改 `frontend/assets/js/pages/chat.js` |

### 2.3 禁止事项
- ❌ 不要在 `ChatAgent` 内做"硬编码的意图分类 / 路由"——保持 LLM 自主决策
- ❌ 不要把高德工具调用逻辑下沉到 `ChatAgent` 之外,否则破坏单 agent 内聚
- ❌ 不要把 `stream_chat` 的 `event` 字段名换掉(前端硬编码)

---

## 3. Claude Code Subagent 角色分配

> 在本项目工作时,按下面的"主 Agent + Subagent 分工"组织任务,避免一个 agent 把所有事都干了。

### 3.1 角色矩阵

| 任务类型 | 默认 Agent | 备注 |
| --- | --- | --- |
| 阅读代码 / 找文件 / 理解结构 | `Explore` | 只读,不修改文件 |
| 编写实现方案 / 改动前出计划 | `Plan` | 只读,产出可审阅的实施步骤 |
| 跨多文件重构、跑命令、修改代码 | `general-purpose` | 默认工作 agent |
| 配置 Claude Code 自身 | `statusline-setup` | 仅在改 `settings.json` 时 |
| 学术研究 / 长报告(本项目不直接相关) | ARS 插件 agents | 仅当用户显式要求时调用 |

### 3.2 并行约束
- `Explore` 与 `Plan` 都是只读 agent,**可以与编辑型 agent 并行**
- 同时启动多个 `general-purpose` agent 修改文件时,要意识到它们之间没有文件锁——同一文件并行编辑会丢失改动
- 单文件深度重构:用**一个** `general-purpose` 串行完成,不要拆分

### 3.3 何时该用 Subagent(而非自己干)
- 需要在 ≥3 个文件里找东西 → 派给 `Explore`
- 改动会触及 ≥3 个文件 / 改动前需要架构权衡 → 先派给 `Plan` 拿计划再动手
- 验证「这个错误信息可能由哪些文件引起」→ `Explore` 比 Read/grep 循环更省上下文

### 3.4 何时**不**该用 Subagent
- 改一个 5 行 bug、查一个变量定义 → 直接 Edit/Grep,不要派 subagent
- 任务的关键证据你手上已经掌握 → 不要让 subagent 重新发现
- 任务是"在 A 文件改 B 行为"这种一行能描述的事 → 自己做

---

## 4. 工作流协议

### 4.1 标准三段式
1. **理解**:`Explore` 读相关文件,产出**结论**(不是文件 dump)
2. **计划**:`Plan` 设计改动,产出**步骤**与**风险**
3. **执行**:`general-purpose` 或主对话自身按计划改代码,改完跑一次 `python -m backend.app` 做烟雾测试

### 4.2 改 `ChatAgent` / `amap_mcp` 工具的协议(硬性)
1. `Explore` 列出所有调用点(前端 `chat.js`、后端 `app.py` 路由)
2. 修改 `amap_mcp.py::tools()` 的 schema → **同步**更新 `summarize_amap_result()` → **同步**更新 `chat_agent.py` 的事件 payload(如果新增字段)
3. 改 `ChatAgent.stream_chat` 的事件 schema → **同步**更新 `frontend/assets/js/pages/chat.js` 的事件处理分支
4. 提交前手测:发一条"从北京南站到故宫"的聊天,确认 SSE 三类事件都能被前端正确消费

### 4.3 改行程生成(`travel_planner.py`)的协议
- System Prompt 是单点真理;**改之前**先确认 `plan.html` 输出区与 `plan-detail.html` 解析对它的假设(目前依赖 `marked.js` 解析)
- 改 Markdown 模板结构时,需要确认 `App.render()` 能正确处理

### 4.4 改前端页面的协议
- 公共能力(主题、Toast、复制、API 调用)必须走 `App` 单例,不要在页面脚本里另起炉灶
- 新增 CSS 颜色/间距一律用 `main.css` 里的 CSS 变量,不要硬编码
- 任何 `innerHTML` 写入的用户输入前必须 `App.escapeHtml`

---

## 5. 跨 Agent 通信与上下文管理

### 5.1 上下文传递
- **主对话 → Subagent**:用 `Agent` 工具的 `prompt` 字段直接描述任务,不要把整段对话历史灌进去(成本高且容易泄露)
- **Subagent → 主对话**:Subagent 给出**结论性总结**,主对话不再二次扒文件
- 当 subagent 返回的结论依赖具体文件/行号时,主对话要在行动前**自己**再 Read 一次确认(因为 subagent 看到的是它那时的快照)

### 5.2 记忆
- 项目级长期事实(架构、关键文件位置)写在 `CLAUDE.md`,**不要写到 memory**
- 用户偏好(沟通风格、个人习惯)写到 `~/.claude/projects/.../memory/MEMORY.md`
- 临时性的"这次会话要做的 5 件事"用 TaskList,**不要写到 memory**

---

## 6. 禁止事项(硬性)

### 6.1 配置 / 安全
- ❌ 不要在代码里硬编码任何 API Key(LLM / 高德 / 其他)
- ❌ 不要把 `data/config.yaml` 或 `plans/*.md` 提交到 git
- ❌ 不要把 CORS `allow_origins=["*"]` 带到生产配置(目前仅用于本地)

### 6.2 代码风格
- ❌ 不要为前端引入 npm 依赖;本项目刻意保持纯静态
- ❌ 不要在 `backend/` 引入 SQLAlchemy / Django / 大型框架
- ❌ 不要把 `ChatAgent` 的流式事件类型改名;前端硬编码
- ❌ 不要在 `amap_mcp.py::call_tool` 外再做 LLM tool_call 解析

### 6.3 协作
- ❌ 不要让 subagent 直接 commit / push;改动由主对话审核后再交
- ❌ 不要并行启动多个 agent 编辑同一文件
- ❌ 不要让 subagent 修改 `CLAUDE.md` 或 `AGENTS.md`——这两份是项目级规范,只接受人工改动

---

## 7. 角色检查清单(Subagent 开工前自查)

> 主对话每次派 subagent 之前,在 prompt 中至少交代清楚以下 5 点:

1. **目标**:一句话说清要达成什么
2. **范围**:可以动哪些文件 / 不可以动哪些文件
3. **依赖**:是否需要先读某个文件、某个 API、某个配置
4. **输出格式**:要的是「代码改动」还是「结论性报告」还是「文件列表」
5. **禁区**:硬性不要做的事(如「不要修改 ChatAgent 事件 schema」)

---

## 8. 单一真理源(参考索引)

| 主题 | 位置 |
| --- | --- |
| 项目总览 / 启动 / API | `CLAUDE.md` |
| UI 设计规范 | `UI界面.md` |
| 后端入口 | `backend/app.py` |
| 运行时唯一 agent | `backend/chat_agent.py` |
| 工具定义 | `backend/amap_mcp.py::tools()` |
| LLM 客户端 | `backend/llm_client.py` |
| 配置 schema | `backend/app.py::FullConfig` + `backend/config_store.py::DEFAULT_CONFIG` |
| 前端全局工具 | `frontend/assets/js/common.js` |
| SSE 事件 schema | `backend/chat_agent.py::stream_chat` ↔ `frontend/assets/js/pages/chat.js` |
