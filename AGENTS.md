# AGENTS.md · 协作智能体任务分工与接口契约

> 本文件定义本仓库可委派的「子智能体 / 子任务（Subagent）」的分工、边界与交付物。
> 技术栈：前端原生 HTML/CSS/JS，后端 Python FastAPI。子任务间通过后端 HTTP API 与 `data/` 数据文件通信。

---

## 0. 通用约定

- 技术栈硬约束：前端原生 HTML/CSS/JS（禁框架、禁 CDN），后端 FastAPI。
- **视觉必须遵循 CLAUDE.md 的三主题设计系统（HUD / CREAM / COMIC）**：新增样式走 CSS 变量与覆盖层（`neon.css` / `comic.css`），不硬编码配色；新页面必须同时适配三套主题。
- **预览统一走弹窗**（固定大小 + 超长滚动），无实时预览。
- 所有 AI 请求前用 `window.LLMSettings.inject(body)` 注入 baseurl/apikey/model。
- 静态资源引用带版本号（`?v=N`），改样式后递增防缓存。
- 聊天消息渲染统一走 `js/hud.js` 的 `window.HudRender.message()`（Markdown + think 折叠块）。

## 1. 后端子任务（FastAPI）

### 1.1 resumes-agent（简历档案服务）✅
- 职责：多档案 CRUD、JSON Schema 校验、sharedProfile 同步、持久化到 `data/resume-files.json`。
- 交付：`services/resumes_service.py`、`routers/resumes.py`。

### 1.2 render-agent（模板渲染 + 导出）✅
- 职责：简历 → HTML 渲染（4 模板）、`/export/html`、`/export/pdf`（Playwright 降级系统浏览器）、`/export/pdf-html`（直接导出 AI 生成的完整 HTML）。
- 交付：`templates/`、`services/pdf_export.py`。

### 1.3 llm-agent（AI 能力）✅
- 职责：OpenAI 兼容客户端（含 JSON 兜底提取与降级重试）；`/resume/polish` 润色；`/resume/ai-chat` 对话生成简历；`/resume/ai-design` **双路并行生成两版 HTML 排版**。
- 交付：`llm/client.py`、`services/resume_llm.py`、`services/ai_generate.py`、`services/ai_design.py`、`routers/ai.py`。
- 约定：未配置 key 时返回 400 + 友好中文提示；生成结果须符合 `resume.schema.json`；排版失败前端有兜底模板，弹窗绝不空白。

### 1.4 interview-agent（对话式模拟面试）✅
- 职责：`/interview/ai-chat` 基于简历提问；**简历来源支持档案或导入 PDF**（`/interview/parse-pdf`：PyMuPDF 抽文本，扫描件调多模态模型 OCR）。
- 交付：`services/interview_service.py`、`services/pdf_parse.py`、`routers/ai.py`。

### 1.5 jobs-agent（岗位雷达）✅
- 职责：岗位库读取（`backend/app/data/jobs.csv`，mtime 缓存、容忍缺列、用户可替换）、筛选排序、本地匹配算法（技能 50%/经验 30%/学历 20%，支持结构化简历与 PDF 文本）。
- 交付：`services/jobs_service.py`、`routers/jobs.py`、`data/jobs.csv`。

## 2. 前端子任务（原生 HTML/CSS/JS）

### 2.1 editor-agent（简历工作台）✅
- 职责：档案管理、角色档案、教育/内容模块、技能、版式设置、「生成预览」弹窗、AI 润色对比面板。
- 交付：`studio.html`、`js/studio.js`、`css/style.css`。

### 2.2 ai-generate-ui（AI 一键生成）✅
- 职责：对话式收集背景 → 一键生成简历（**带进度条**）→ **双版 AI 排版弹窗**（二选一/重新生成）→ 存档/导出。
- 交付：`ai-create.html`、`js/ai-create.js`、`css/ai-create.css`。

### 2.3 settings-ui（LLM 设置）✅
- 职责：`js/settings.js` 提供 `window.LLMSettings`（open/get/inject），baseurl+apikey+model 存 localStorage。

### 2.4 interview-ui（AI 面试）✅
- 职责：面试设置（档案/PDF 来源切换、公司/岗位/JD）、对话区（Markdown + think 折叠渲染）。
- 交付：`interview.html`、`js/interview.js`、`css/interview.css`。

### 2.5 jobs-ui（岗位雷达）✅
- 职责：统计条、关键词/城市/类别筛选、排序、岗位卡（匹配度环）、详情弹窗（结构化 JD 分节 + 技能命中对照 + 匹配分解）、PDF 简历上传。
- 交付：`jobs.html`、`js/jobs.js`、`css/jobs.css`。

### 2.6 theme-ui（三主题系统）✅
- 职责：`js/theme.js` 主题循环引擎（HUD/CREAM/COMIC，localStorage 持久化，全站同步）；`css/neon.css`（CREAM）、`css/comic.css`（COMIC）覆盖层。
- 约定：新页面/新组件必须提供三主题样式；覆盖层按 `html[data-theme="..."]` 前缀书写。

## 3. 跨子任务接口清单

| 调用方 | 接口 | 用途 |
|---|---|---|
| editor / ai-generate | `GET /resume-files`、`GET/POST/PUT/PATCH/DELETE /resume-files/...` | 档案管理 |
| editor / ai-generate | `POST /export/html`、`POST /export/pdf`、`POST /export/pdf-html` | 渲染/导出（键名 `templateId`） |
| editor | `POST /resume/polish` | AI 润色 |
| ai-generate | `POST /resume/ai-chat` | 对话生成简历 JSON |
| ai-generate | `POST /resume/ai-design` | 双路并行生成两版排版 `{versions:[{name,desc,html}]}` |
| interview | `POST /interview/ai-chat` | 对话式面试（`resumeText` 或 `resumeFileId`） |
| interview / jobs | `POST /interview/parse-pdf`（multipart） | PDF 解析（文本抽取 + OCR 兜底） |
| jobs | `GET /jobs`、`POST /jobs/match`（`resume` 或 `resumeText`） | 岗位列表 / 匹配度 |
| 页面 | `GET /`、`/studio`、`/ai-create`、`/interview`、`/jobs` | 页面路由 |

## 4. 交付物与验收

| 子任务 | 状态 | 验收要点 |
|---|---|---|
| resumes-agent | ✅ | CRUD/校验/持久化正常 |
| render-agent | ✅ | 4 模板渲染、预览完整、PDF/pdf-html 可导出 |
| llm-agent | ✅ | 润色/生成/双版排版返回结构正确，缺配置有友好提示，排版失败有兜底 |
| interview-agent | ✅ | 档案/PDF 两来源面试可用，PDF 扫描件 OCR 兜底 |
| jobs-agent | ✅ | CSV 热加载、筛选排序、匹配算法正确 |
| editor-agent | ✅ | 编辑/预览弹窗/存档/润色可用，三主题视觉正确 |
| ai-generate-ui | ✅ | 对话→生成→进度条→双版排版弹窗→存档闭环 |
| settings-ui | ✅ | 设置弹窗可用，配置持久化 |
| interview-ui | ✅ | PDF 导入/对话/点评闭环 |
| jobs-ui | ✅ | 筛选/匹配/详情/PDF 上传闭环 |
| theme-ui | ✅ | 三主题循环切换、持久化、全站一致 |

> 派发任何子任务前，先让其读 CLAUDE.md（尤其三主题设计系统 §3 与关键约定 §5）。

## 5. 启动

```bash
python run.py            # 一键启动（自动建 venv + 装依赖），默认 0.0.0.0:8000
```
详见 CLAUDE.md §8。
