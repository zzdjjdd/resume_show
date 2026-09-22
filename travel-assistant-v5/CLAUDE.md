# CLAUDE.md — AI 智行助手 (智能出行小助手 v5)

> Claude Code 上下文文档。打开此项目时,请先读本文件了解全貌再行动。

---

## 1. 项目概述

**AI 智行助手** 是一款「端云协同」的智能出行管家,后端使用 FastAPI,前端为原生 HTML/CSS/JS,核心能力由「可配置 LLM」+「高德地图 MCP 工具」驱动,提供两种模式:

| 模式 | 入口 | 关键能力 |
| --- | --- | --- |
| **旅游模式** | `/plan`、`/plan-detail` | 输入出发地/目的地/天数/人数/偏好,LLM 生成结构化 Markdown 行程,并保存为 `plans/*.md` |
| **日常聊天** | `/chat` | 自然语言对话,涉及位置/路线/POI/天气时 LLM 自动调用高德 MCP 工具,流式 SSE 输出思考过程 + 工具卡片 + 正文 |

设计风格遵循 `UI界面.md` 描述的 **Neo-Brutalism**(粗野主义)美学:硬边、饱和色块、粗描边、平移阴影。

---

## 2. 技术栈

### 后端 (`backend/`)
- **Python 3.10+** / **FastAPI 0.115** / **Uvicorn 0.32**
- **httpx 0.27** — 异步 HTTP 客户端(同时用于 LLM API 与高德 REST API)
- **Pydantic 2.9** — 请求/响应数据模型
- **PyYAML 6.0** — 配置文件读写
- 不引入 ORM/数据库;数据落盘到 `data/config.yaml` 与 `plans/*.md`

### 前端 (`frontend/`)
- 原生 HTML5 + ES6+ JS,**不依赖任何前端框架**
- **marked.js** (CDN) — Markdown 渲染
- 单一全局 `App` 单例(`common.js`),封装 API 请求、主题、Toast、复制、滚动进度等
- CSS 变量驱动的主题系统(`auto` / `light` / `dark`),通过 `data-theme` 切换

### 外部依赖
- **LLM**:任何 OpenAI 兼容服务(默认 `https://api.openai.com/v1` · `gpt-4o-mini`,支持 DeepSeek / 硅基流动 / 自部署代理等)
- **高德地图**:`https://restapi.amap.com/v3`(Web 服务 Key),通过 9 个 REST 端点模拟 MCP 工具语义

---

## 3. 目录结构

```
travel-assistant-v5/
├── CLAUDE.md                       # 本文件(项目上下文)
├── UI界面.md                        # UI 设计规范(Neo-Brutalism)
├── backend/                        # FastAPI 后端
│   ├── __init__.py
│   ├── app.py                      # FastAPI 入口,挂载路由 + 静态前端
│   ├── config_store.py             # YAML 配置读写
│   ├── llm_client.py               # 统一 LLM 客户端(OpenAI 兼容)
│   ├── amap_mcp.py                 # 高德 MCP 工具桥接(9 个工具 + 结果摘要)
│   ├── travel_planner.py           # 旅游行程生成(System Prompt + LLM 调用)
│   ├── chat_agent.py               # 聊天 Agent(工具调用 + 流式 + 思考过程)
│   └── requirements.txt
├── frontend/                       # 原生前端
│   ├── index.html                  # 首页(三幕叙事 + Hero)
│   ├── plan.html                   # 旅游模式(参数表单 + 行程预览 + 历史)
│   ├── plan-detail.html            # 行程详情(独立可打印页面)
│   ├── chat.html                   # 日常聊天(流式 SSE)
│   ├── config.html                 # 设置(LLM + 高德 Key)
│   └── assets/
│       ├── css/main.css            # 全局样式 + Neo-Brutalism 主题
│       ├── css/plan-detail.css     # 行程详情专用样式
│       ├── js/common.js            # 全局 App 单例(API/主题/Toast/复制/...)
│       └── js/pages/
│           ├── plan.js             # 行程生成 + 历史列表
│           ├── plan-detail.js      # 行程详情渲染(marked.js)
│           ├── chat.js             # SSE 解析 + 思考过程 + 工具卡片
│           └── config.js           # 设置表单交互
├── data/                           # 运行时生成
│   └── config.yaml                 # LLM / 高德 / MCP / UI 配置
└── plans/                          # 行程历史(由后端生成)
    └── plan_YYYYMMDD_HHMMSS_xxxxxx.md
```

> `data/` 与 `plans/` 均为运行时自动创建,不应纳入版本控制(建议加入 `.gitignore`)。

---

## 4. 快速开始

### 4.1 安装依赖

```bash
cd "travel-assistant-v5"
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r backend/requirements.txt
```

### 4.2 启动后端

```bash
# 方式 A:作为模块运行(推荐)
python -m backend.app

# 方式 B:显式 uvicorn
uvicorn backend.app:app --host 0.0.0.0 --port 8765
```

服务启动后,浏览器访问 <http://localhost:8765/>。

> `backend/app.py` 末尾默认 `uvicorn.run("backend.app:app", host="0.0.0.0", port=8765)`。

### 4.3 首次配置

打开 `/config` 页面:
1. 填入 **LLM API Key / Base URL / Model**(可点「获取模型」自动下拉);支持任意 OpenAI 兼容接口
2. 填入 **高德 Web 服务 API Key**(到 <https://lbs.amap.com/> 申请)
3. 点「测试连接」验证,再点「保存」

---

## 5. 后端架构

### 5.1 模块职责

| 模块 | 职责 | 关键约束 |
| --- | --- | --- |
| `config_store.py` | 读/写 `data/config.yaml`,提供默认值与递归 merge | 文件写入加 `Lock` 防并发 |
| `llm_client.py` | 统一 LLM 客户端,支持非流式 `chat` 与流式 `stream_chat` | 任何 OpenAI 兼容服务都可用;支持 `reasoning_split` 让思考内容分离 |
| `amap_mcp.py` | 定义 9 个 OpenAI function-call 格式工具 + 真实 REST 调用 + 结果摘要 | 工具 schema 必须与 LLM 期望一致 |
| `mcp_client.py` | 通用 MCP 客户端(JSON-RPC 2.0 over HTTP/SSE),启动时 `tools/list` 动态发现 | 工具名加 `mc_` 前缀避免与 amap 冲突;支持 SSE 流式响应 |
| `travel_planner.py` | 行程生成:固定 System Prompt(中英 Markdown 模板) → 单轮 LLM 调用 | `temperature=0.8` 提升多样性 |
| `chat_agent.py` | 聊天 Agent:多轮工具调用循环(默认 6 轮) + 思考过程抽取 + 流式事件 | 抽取 `reasoning_details` / `reasoning` / `reasoning_content` 多种风格的思考内容 |
| `app.py` | FastAPI 路由 + CORS + 静态前端挂载 | 启动期 `lifespan` 钩子负责 MCP 初始化 |

### 5.2 API 路由总览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查 |
| GET | `/api/config` | 读取完整配置 |
| POST | `/api/config` | 写入完整配置 |
| POST | `/api/config/llm` | 仅更新 LLM 段 |
| POST | `/api/config/amap` | 仅更新高德段 |
| POST | `/api/config/mcp` | 仅更新 MCP 段(server_url / enabled / timeout) |
| POST | `/api/test/llm` | 测试 LLM 连接(支持 override) |
| POST | `/api/test/amap` | 测试高德 Key(用 `maps_geo` 探活) |
| POST | `/api/test/mcp` | 测试 MCP 连接(临时 override),返回工具数量 + 前 10 个 tool 名 |
| GET | `/api/mcp/tools` | 返回已加载的 MCP 工具(供设置页展示) |
| POST | `/api/mcp/refresh` | 强制重新 initialize + list_tools(必须已启用) |
| POST | `/api/mcp/call` | 手动调用单个 MCP 工具(供前端测试) |
| POST | `/api/llm/models` | 拉取远端模型列表 |
| POST | `/api/travel/plan` | 生成旅游行程 + 落盘到 `plans/` |
| GET | `/api/travel/plans` | 列出所有历史行程 |
| GET | `/api/travel/plan/{plan_id}` | 读取单个行程 Markdown |
| POST | `/api/chat` | 非流式聊天 |
| POST | `/api/chat/stream` | SSE 流式聊天(thinking / tool / content / done 事件) |
| GET | `/` / `/plan` / `/chat` / `/config` | 静态页面 |

### 5.3 工具定义(`amap_mcp.py` → `tools()`)

返回 9 个 `type: function` 工具供 LLM 调用:
- `maps_geo` / `maps_regeocode` — 地理编码 / 逆编码
- `maps_text_search` / `maps_around_search` — 关键词 / 周边 POI
- `maps_direction_driving` / `maps_direction_walking` / `maps_direction_transit_integrated` — 路径规划
- `maps_distance` — 距离测量
- `maps_weather` — 天气

> 实际通过 `https://restapi.amap.com/v3/...` REST 调用;`summarize_amap_result()` 把冗长 JSON 压成可读中文摘要回灌给 LLM。

### 5.4 外部 MCP 集成(`mcp_client.py`)

支持任意标准 MCP 端点(URL 自带 token,无需 API Key)。在设置页填入 `mcp.server_url` 并勾选 `enabled`,**重启后端**后启动期自动 `initialize + tools/list`,动态发现 tool 列表。

- **协议**:JSON-RPC 2.0 over HTTP,自动兼容 `text/event-stream` 流式响应
- **工具名前缀**:`mc_`(避免与 amap 9 个工具冲突),LLM 在调用时看到的就是 `mc_train_search` 等
- **配置**:`data/config.yaml` 的 `mcp` 段:`{server_url, enabled, timeout}`
- **新增工具无需改代码**:服务端 `tools/list` 返回什么,前端聊天流就出现什么卡片

---

## 6. 前端约定

### 6.1 全局 `App` 单例

`common.js` 暴露以下方法,所有页面脚本都应使用:

| 方法 | 用途 |
| --- | --- |
| `App.api(path, { method, body })` | 统一 fetch;自动 JSON 序列化,自动解析 JSON/text |
| `App.render(el, md)` | 把 Markdown 渲染到容器并加 `md-body` 类 |
| `App.renderMarkdown(text)` | 仅返回 HTML 字符串 |
| `App.copy(text)` | 复制到剪贴板(自动降级到 `execCommand`) |
| `App.toast(msg, type)` | 右上角提示(`success` / `error` / `info`) |
| `App.escapeHtml(s)` | 防御性 HTML 转义 |
| `App.applyTheme(theme)` / `App.initTheme()` | 主题切换与初始化 |
| `App.loadServerConfig()` / `App.saveServerConfig(cfg)` | 配置读写 |

### 6.2 主题系统

- 根 `<html>` 上加 `data-theme="light|dark"`,缺省为 `auto`(跟随系统)
- `localStorage.theme` 持久化
- 切换循环:`auto` → `dark` → `light` → `auto`
- 颜色全部由 CSS 变量驱动(`--bg-*`, `--fg-*`, `--accent`, `--border-default` 等),新增组件请沿用变量

### 6.3 页面脚本规范

- 每个页面 HTML 末尾引入 `common.js` + 对应 `pages/<name>.js`
- 页面脚本用 `document.addEventListener('DOMContentLoaded', () => { ... })` 包裹
- 元素引用统一 `const $ = (id) => document.getElementById(id);`
- 事件绑定后,重复 ID 的 `onclick = ...` 写法用于动态生成的元素

### 6.4 聊天流协议(`/api/chat/stream`)

SSE 事件 `data: {json}\n\n`,事件类型:
- `thinking` — `{ event, delta }` 可多次
- `tool` — `{ event, name, arguments, status: 'running'|'done', summary? }`
- `content` — `{ event, delta }` Markdown 增量
- `done` — `{ event, tools_used, reasoning, error? }`

---

## 7. UI 设计规范(摘自 `UI界面.md`)

- **视觉**:粗线框(2-4px border)、大圆角或硬角色块、饱和糖果色(粉/黄/蓝/绿)、粗黑/等宽字体、短而偏移明确的阴影
- **材质**:实心填充、噪点/条纹背景、贴纸/涂鸦元素;避免过度玻璃与渐变
- **交互**:Hover 轻微旋转或上浮 + 阴影加粗;Active 下沉/收敛;过渡 120-200ms
- **整体**:张扬、俏皮但有秩序,像彩色积木构成的界面

> 改动 UI 前先看 `frontend/assets/css/main.css` 的色板与间距变量,保持视觉一致。

---

## 8. 开发规范

### 8.1 Python 风格
- 模块顶部 docstring 写明职责
- 异步优先(LLM/HTTP 都用 `async/await`)
- Pydantic 模型集中在 `app.py` 顶部;新增请求模型放同一处
- 错误处理:`return {"success": False, "error": "..."}` 或抛 `HTTPException`;**不要静默吞异常**
- 配置改动走 `config_store.save_config()`,不要绕开

### 8.2 JavaScript 风格
- 不引入任何 npm 依赖,保持单文件可静态托管
- 用 `const` / `let`,避免 `var`
- DOM 操作优先 `textContent` / `createElement`,少用 `innerHTML`;必须用时对用户输入走 `App.escapeHtml`

### 8.3 安全与隐私
- API Key 仅保存在本地 `data/config.yaml`,不外发
- CORS 设为 `*` 仅用于本地开发,部署前请收紧
- LLM 响应的内容在写入 `plans/*.md` 与返回前端前应保持原样,不在后端做截断
- 用户输入在 `App.escapeHtml` 之后才能拼接进 `innerHTML`

### 8.4 新增功能流程
1. 后端:`backend/` 新增模块,路由挂到 `app.py`;Pydantic 模型加在 `app.py` 顶部
2. 前端:`frontend/` 新增/修改 HTML,JS 加在 `assets/js/pages/`,UI 元素沿用 `main.css` 变量
3. 如需新工具:在 `amap_mcp.py` 的 `tools()` 加 schema → 在 `call_tool()` 加分支 → 在 `summarize_amap_result()` 加摘要
4. 改动 `config.yaml` 结构:同步更新 `DEFAULT_CONFIG` 与 `FullConfig` 模型

### 8.5 提交前自检
- [ ] `python -m backend.app` 可正常启动
- [ ] `/` `/plan` `/chat` `/config` 四个页面都能打开
- [ ] 配置页「测试连接」通过
- [ ] 至少跑通一次「生成行程 + 查看详情」与「聊天 + 工具调用」

---

## 9. 常见问题(故障排查)

| 现象 | 可能原因 | 处理 |
| --- | --- | --- |
| `/api/test/llm` 返回 `HTTP 401` | Base URL 或 API Key 不对 | 检查 `config.yaml` 或在「设置」中重填 |
| `/api/test/llm` 返回 `HTTP 404` | Base URL 路径错误(已自动补齐 `/v1/models`) | 把 `base_url` 改成根域名,如 `https://api.openai.com/v1` |
| 「生成行程」一直转圈 | LLM 慢或思考链过长 | 把 `timeout` 调到 120-300;切换更快的模型 |
| 「聊天」报「高德 API Key 为空」 | 未配置高德 | 在「设置」填入高德 Web 服务 Key |
| 主题切换后页面错位 | CSS 变量未覆盖 | `main.css` 必须始终参与,不要替换整个样式 |
| 历史计划加载失败 | `plans/` 目录权限 | 确认进程对该目录有读写权限 |

---

## 10. 许可证与备注

- 项目内代码仅供学习与个人使用
- 高德地图 API 调用受高德开放平台条款约束
- LLM 调用受所选服务商条款约束;**请勿在生产环境硬编码任何 API Key**
