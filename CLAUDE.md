# CLAUDE.md · Resume Agent（FastAPI 版）工程约定

> 本项目是原 `Resume-agent-main`（Next.js + NestJS）的**重写版**：前端原生 HTML+CSS+JS，后端 Python FastAPI。
> 本文件是当前工程的**权威约定**，后续开发以此为准（聚焦最近需求）。

---

## 0. 当前状态速览

| 模块 | 状态 |
|---|---|
| Landing 首页（`/`） | ✅ |
| 简历工作台（`/studio`）：编辑 + 预览弹窗 + AI 润色 | ✅ |
| AI 一键生成简历（`/ai-create`）：对话 → 生成 → **双版 AI 排版**弹窗 + 进度条 | ✅ |
| AI 对话式模拟面试（`/interview`）：**档案或导入 PDF** 两种简历来源 | ✅ |
| **岗位雷达（`/jobs`）**：岗位库 + 本地匹配度 + PDF 简历上传 | ✅ |
| **三主题**：HUD / CREAM / COMIC，顶栏循环切换、localStorage 持久化 | ✅ |
| LLM 设置弹窗（baseurl + apikey + model） | ✅ |
| 一键启动脚本 `run.py`（自动建 venv + 装依赖 + 启动） | ✅ |

---

## 1. 技术栈（硬约束）

- **前端**：原生 HTML + CSS + JavaScript，**禁止**引入 React/Vue/Next.js 等框架，禁止 CDN 依赖。
- **后端**：Python FastAPI + Uvicorn。
- **依赖**（`backend/requirements.txt`）：`fastapi / uvicorn / pydantic / python-dotenv / httpx / jsonschema / playwright / pymupdf / python-multipart`。
- **PDF 导出**：优先 Playwright 无头 Chromium；无则降级系统 Chrome/Edge `--print-to-pdf`（`services/pdf_export.py`）。`/export/pdf-html` 支持直接导出 AI 生成的完整 HTML。
- **PDF 解析**（`services/pdf_parse.py`）：PyMuPDF 抽文本层；文本过少（<80 字，疑似扫描件）时渲染 PNG 调**多模态模型 OCR**。
- **LLM**：OpenAI 兼容协议。前端 `js/settings.js` 提供 `window.LLMSettings`（`open()/get()/inject(body)`），baseurl/apikey/model 存 localStorage，请求时注入 body。

## 2. 目录结构

```
resume-agent-fastapi/
├── run.py                      # ★ 一键启动（建 venv + 装依赖 + uvicorn，host/port 可配）
├── backend/app/
│   ├── main.py                 # FastAPI 入口：页面路由 + 挂载 routers + /static 托管
│   ├── config.py               # env / 路径 / LLM 配置（INTERVIEW_* / DASHSCOPE_* / OPENAI_*）
│   ├── utils.py
│   ├── llm/client.py           # OpenAI 兼容客户端（chat / chat_json，带 JSON 兜底提取与降级重试）
│   ├── routers/
│   │   ├── resumes.py          # 简历 CRUD + 模板 + 导出 + 润色 + /export/pdf-html
│   │   ├── ai.py               # /resume/ai-chat、/resume/ai-design、/interview/parse-pdf、/interview/ai-chat
│   │   └── jobs.py             # /jobs、/jobs/match（Accept 协商同路径返回页面或 JSON）
│   ├── schemas/resume_models.py
│   ├── services/
│   │   ├── resumes_service.py  # 简历多档案 CRUD + JSON Schema 校验 + 持久化
│   │   ├── resume_llm.py       # AI 润色
│   │   ├── ai_generate.py      # AI 对话生成简历 JSON
│   │   ├── ai_design.py        # ★ 双路并行生成两版 HTML 排版（防超长截断）
│   │   ├── interview_service.py# 对话式面试（支持 resume 或 resume_text）
│   │   ├── pdf_parse.py        # ★ PDF 文本抽取 + OCR 兜底
│   │   ├── jobs_service.py     # ★ 岗位 CSV 读取(mtime 缓存) + 本地匹配算法
│   │   └── pdf_export.py
│   ├── data/jobs.csv           # ★ 岗位示例数据（用户可替换，表头见 §6）
│   └── templates/              # 简历 -> HTML 渲染（4 套模板）
│       ├── templates_service.py  render_helpers.py
│       └── layouts/{single_column,modern_templates}.py
├── frontend/
│   ├── index.html  css/style.css                    # Landing
│   ├── studio.html js/studio.js                     # 工作台
│   ├── ai-create.html js/ai-create.js css/ai-create.css  # AI 生成 + 进度条 + 预览弹窗
│   ├── interview.html js/interview.js css/interview.css  # AI 面试 + PDF 导入
│   ├── jobs.html js/jobs.js css/jobs.css            # ★ 岗位雷达
│   ├── css/neon.css    # CREAM 奶白主题覆盖层
│   ├── css/comic.css   # ★ COMIC 漫画主题覆盖层
│   └── js/theme.js     # ★ 三主题循环切换引擎   js/hud.js 时钟+Markdown   js/settings.js LLM 设置
├── data/  schemas/  .env.example  start.ps1
└── CLAUDE.md  AGENTS.md  PRD.md
```

## 3. 三主题设计系统（全站必须遵循）

顶栏 `#theme-toggle` 按钮循环切换，`js/theme.js` 管理（`ORDER=["hud","neon","comic"]`），写 `html[data-theme]` 与 localStorage（键 `resume-agent-theme`），全站同步。

| 主题 | 内部键 | 风格 | 关键 token |
|---|---|---|---|
| **HUD**（默认） | `hud` | 深空暗色、青蓝发光、战术网格+扫描线 | 背景 `#020617→#0f172a`，强调 `#22d3ee/#0ea5e9`，玻璃面板 `rgba(15,23,42,.72)` |
| **CREAM** | `neon` | 奶白明亮、简洁 | 背景 `#fdfcf9→#f1f2f6`，强调靛紫渐变 `#6366f1→#a855f7→#ec4899`（变量前缀 `--n-`，覆盖层 `css/neon.css`） |
| **COMIC** | `comic` | 漫画书：纸张白+半色调网点、CMYK 原色、纯黑粗描边、硬偏移阴影、气泡尾巴、卡片微倾斜 | 纸张 `#FFFEF0`、红 `#E23636`/蓝 `#1E90FF`/黄 `#FFD700`、描边 `#101010`（覆盖层 `css/comic.css`） |

- 基础样式与变量在 `css/style.css`（HUD 基调）；CREAM/COMIC 是**覆盖层**，按 `html[data-theme="..."]` 前缀覆写，勿改 `style.css` 基础结构。
- 颜色一律走 CSS 变量，禁止散落硬编码；改页面前先复用现有变量与类。
- **静态资源引用统一带版本号**（如 `static/css/style.css?v=3`），改样式后递增 `?v=N` 防浏览器缓存。

## 4. 页面与路由

| 页面 | 路由 | 顶栏 | 说明 |
|---|---|---|---|
| Landing | `/` | `.glass-nav` + HUD 状态带 | 营销首屏 |
| 工作台 | `/studio` | `.studio-topbar` | 侧栏(档案/模板/版式) + 编辑区 + 预览弹窗 + AI 润色 |
| AI 生成 | `/ai-create` | `.aic-topbar` | 单列对话；生成后**弹窗预览双版排版**；一键生成带**进度条** |
| AI 面试 | `/interview` | `.aic-topbar` | 左设置(档案/PDF 来源切换) + 右对话 |
| 岗位雷达 | `/jobs` | `.studio-topbar` | 统计 + 筛选 + 岗位卡 + 详情弹窗（结构化 JD + 匹配分解） |

后端页面路由在 `main.py` 的 `_serve_page()`；API 由 `routers/` 提供；静态资源挂载在 `/static`。`/jobs` 同路径按 `Accept` 协商返回 HTML 页面或 JSON。

## 5. 关键约定

1. **预览走弹窗，不做实时预览**。弹窗**固定大小**（`min(920px,100%) × min(94vh,100%)`），iframe 按内容 `scrollHeight` 自适应撑高，弹窗 body `overflow:auto` 超长滚动，绝不裁切、绝不空白。
2. **AI 排版防空白**：`/resume/ai-design` 双路并行各出一版 HTML；前端生成失败时兜底内置模板渲染，弹窗永不空白；生成全程显示进度条（`#gen-progress`，阶段式伪进度）。
3. **聊天渲染**：AI 回复经 `js/hud.js` 的 `window.HudRender.message()` 渲染——支持 Markdown（标题/列表/加粗/斜体/行内代码/引用/链接），并把 `<think>…</think>` 抽成可折叠「思考过程」。历史上下文入库前剔除 think 块。
4. **LLM 设置**：所有 AI 请求前用 `window.LLMSettings.inject(body)` 注入；PDF OCR 与岗位 PDF 上传走 multipart，同样注入 baseUrl/apiKey/model。
5. **岗位数据可替换**：用户用真实 CSV 覆盖 `backend/app/data/jobs.csv` 即可，服务按 mtime 自动重载、容忍缺列。

## 6. 岗位 CSV 表头（`backend/app/data/jobs.csv`）

```
id,title,company,city,category,salary_min,salary_max,experience,education,skills,tags,benefits,description,publish_date
```
- `skills/tags/benefits` 多值用 `|` 分隔；`salary_min/max` 单位 K。
- `description` 用【岗位职责】【任职要求】【技术要求】三节 + 编号换行，前端按分节渲染为列表。
- 匹配算法（`jobs_service.match_resume` / `match_resume_text`）：技能 50% + 经验 30% + 学历 20%；同时支持结构化简历与 PDF 文本。

## 7. 后端约定

- 分层：`routers`（路由/入参）→ `services`（业务）→ `llm/templates`（能力）。
- 业务异常用 `services` 内自定义异常（如 `LlmContentError`/`PdfParseError`/`PdfExportError`），路由捕获返回 `JSONResponse({"detail"})`。
- 简历校验用 `schemas/resume.schema.json`，持久化到 `data/resume-files.json`。
- 简历渲染统一走 `templates_service.render_html(resume, templateId, layout)`。
- FastAPI `Body` 接收**驼峰键名**（如 `templateId`/`resumeText`/`jobId`）必须加 `alias`。
- `llm/client.py` 的 `chat_json` 已带「平衡括号提取 + 代码块剥离 + response_format 降级重试」，新增 JSON 生成类功能直接复用。

## 8. 运行

```bash
# 一键启动（推荐，跨平台）：自动建 venv、装依赖、启动，默认 0.0.0.0:8000
python run.py                 # 可加 --port 9000 / --host 127.0.0.1 / --install / --no-install

# 手动方式
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt       # Windows
.venv/bin/python -m pip install -r requirements.txt           # Linux
.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 云服务器后台常驻（Linux）
nohup python3 run.py > server.log 2>&1 &
```
访问 `http://localhost:8000`（服务器为 `http://服务器IP:8000`）。AI 功能需先在页面「设置」里配置大模型 baseurl + apikey。PDF 精确导出建议 `.venv/.../python -m playwright install chromium`（缺失时自动降级系统浏览器）。
