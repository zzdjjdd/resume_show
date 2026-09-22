# Resume Agent · 产品需求文档（PRD）

> 低门槛、开箱即用的 AI 简历平台。前端原生 HTML/CSS/JS + 后端 FastAPI，单服务部署（`python run.py` 一键启动）。
> 本文档描述**当前已实现**的产品形态。

---

## 1. 产品定位

围绕「求职」提供一条完整服务链，三大视觉主题随心切换：

- **结构化编辑**：多档案管理、模块化编辑器、角色档案（头像/附加信息）、拖拽排序、4 套高端模板、精确 PDF 导出。
- **AI 一键生成**：对话式收集背景 → 生成简历 → **AI 直接设计两版精美排版**（非固定模板）供挑选，可重新生成。
- **AI 智能润色**：按目标 JD 对选中条目做最小改动的强化润色，前后对比 + 下一步建议。
- **AI 模拟面试**：导入简历（档案或 **PDF**），AI 面试官基于简历项目逐题追问、实时点评。
- **岗位雷达**：岗位库浏览 + **简历匹配度分析**（档案或 PDF 上传），技能对照与匹配分解。
- **三主题视觉**：科幻 HUD / 奶白 CREAM / 漫画书 COMIC，顶栏一键循环切换、全站记忆。

---

## 2. 页面结构

| 页面 | 路由 | 说明 |
|---|---|---|
| 首页 | `/` | 营销首屏 + 功能展示 + HUD 状态带 |
| 简历工作台 | `/studio` | 侧栏（档案/模板/版式）+ 编辑区 + 生成预览弹窗 + AI 润色 |
| AI 一键生成 | `/ai-create` | 对话式生成 + 进度条 + 双版排版预览弹窗 |
| AI 模拟面试 | `/interview` | 简历来源（档案/PDF）+ 对话面试 |
| 岗位雷达 | `/jobs` | 岗位库 + 筛选 + 匹配度 + 详情弹窗 |

顶栏通用：主题切换（◐ HUD/CREAM/COMIC）、舰桥时钟、大模型设置入口。

---

## 3. 功能需求

### 3.1 简历工作台
- **档案管理**：多简历文件、默认/当前徽章、新建/删除（至少保留一份）、切换加载。
- **角色档案**：姓名/邮箱/电话/城市、头像上传（dataURL，≤2MB）、附加信息快捷项（求职状态💼/意向岗位🎯/个人网站🔗/研究方向🔬）、个人简介。
- **教育经历**：学校/学位/专业/GPA/学院/起止时间/学校标签/要点，拖拽排序。
- **内容模块**：自定义模块（工作/项目/科研等）+ 条目 + 显示开关 + 拖拽排序。
- **技能**：逗号分隔 + 显示开关。
- **版式设置**：4 模板（现代专业/双栏精英/极简雅致/Modern CN）、主题色、字体、头部对齐、页边距、字号、行高。
- **生成预览**：弹窗固定大小展示，iframe 按内容自适应撑高，超长滚动。
- **AI 润色**：选条目 + 可选 JD → 前后对比面板 + 改动说明 + 下一步建议。

### 3.2 AI 一键生成
- 对话式收集（AI 追问补齐信息），支持快捷场景开场。
- 点「一键生成简历」显示**进度条**（阶段式：分析背景 → 生成简历 → 设计排版）。
- 生成后调 `/resume/ai-design` **双路并行产出两版 HTML 排版**（风格方向 A/B），弹窗内切换预览、可「重新生成」。
- 防空白：AI 排版失败自动兜底内置模板；聊天回复支持 Markdown 渲染与 think 折叠块。
- 存为档案（进工作台继续编辑）/ 导出 PDF。

### 3.3 AI 模拟面试
- **简历来源二选一**：选择档案，或**上传简历 PDF**（PyMuPDF 抽文本；扫描件自动调多模态模型 OCR）。
- 设置目标公司/岗位/JD，AI 面试官基于简历逐题追问，作答后点评并继续提问，可结束并总结。

### 3.4 岗位雷达
- 岗位库来自 `backend/app/data/jobs.csv`（**用户可替换为自己的数据**，服务自动热加载）。
- 每条岗位含结构化 JD：【岗位职责】【任职要求】【技术要求】。
- 统计条（在招数/平均薪资/最高匹配/城市）+ 关键词/城市/类别筛选 + 排序。
- **简历匹配度**：选择档案或上传 PDF，本地计算技能 50%/经验 30%/学历 20% 加权分；详情弹窗展示技能命中对照与三维匹配分解。

### 3.5 主题系统
- HUD（深色战术青）/ CREAM（奶白）/ COMIC（漫画书：纸张网点、粗描边、硬阴影、气泡尾巴）。
- 顶栏按钮循环切换，localStorage 持久化，全站同步。

---

## 4. 数据模型

### 4.1 Resume
```jsonc
{
  "basics": { "name", "email", "phone", "location", "summary", "photo", "extraInfos[]" },
  "education": [{ "school","degree","major","startDate","endDate","gpa","schoolTags","college","summary","highlights[]" }],
  "customSections": [{ "title", "items": [{ "title","org","period","highlights[]" }] }],
  "skills": []
}
```

### 4.2 ResumeFile
```jsonc
{ "id","name","isDefault","createdAt","updatedAt","data":"<Resume>",
  "config": { "templateId","layout":{...},"aiDesignName" } }
```
- 持久化 `data/resume-files.json`；校验 `schemas/resume.schema.json`。

### 4.3 岗位（jobs.csv）
```
id,title,company,city,category,salary_min,salary_max,experience,education,skills,tags,benefits,description,publish_date
```
- `skills/tags/benefits` 用 `|` 分隔；`description` 用【岗位职责】等分节。

---

## 5. 后端 API 契约

- 基础：`GET /`、`/health`、`/resume/sample`
- 简历：`GET/POST /resume-files`、`GET /resume-files/default`、`GET/PUT/PATCH/DELETE /resume-files/:id`、`PATCH /resume-files/:id/default`
- 模板导出：`GET /templates`、`POST /export/html`、`POST /export/pdf`、`POST /export/pdf-html`
- AI：`POST /resume/polish`、`POST /resume/ai-chat`、`POST /resume/ai-design`
- 面试：`POST /interview/ai-chat`、`POST /interview/parse-pdf`（multipart）
- 岗位：`GET /jobs`、`POST /jobs/match`

---

## 6. 非功能需求

- 技术栈：前端原生 HTML/CSS/JS；后端 FastAPI；单服务部署。
- LLM：OpenAI 兼容，页面「设置」配置 baseurl/apikey/model，未配置清晰提示。
- PDF 导出：Playwright 优先，降级系统浏览器；PDF 解析：PyMuPDF + 多模态 OCR 兜底。
- 三主题视觉一致；聊天 Markdown + think 折叠渲染；预览弹窗固定大小 + 超长滚动。
- 友好错误、删除确认、转义防 XSS。

---

## 7. 里程碑（已完成）

- ✅ 简历编辑 + 润色 + 4 模板 + PDF 导出
- ✅ AI 对话生成 + 双版 AI 排版 + 进度条
- ✅ AI 模拟面试 + PDF 导入（OCR 兜底）
- ✅ 岗位雷达 + 匹配度分析 + CSV 可替换数据源
- ✅ 三主题（HUD / CREAM / COMIC）+ `run.py` 一键部署
