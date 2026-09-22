# 项目集 · Projects

个人项目集合：覆盖 LLM 应用、Agent 智能体、RAG 检索增强、大模型微调与工程落地。
每个子目录都是一个**独立可运行的项目**，各自带有 `README.md`、`LICENSE`、`.gitignore`。

---

## 项目一览

| 项目 | 是什么 | 技术栈 | 规模 |
|---|---|---|---|
| [**memoria**](memoria/) | Agent 的短期 + 长期记忆模块：四层认知模型（工作/情景/语义/程序），向量库 + SQLite 混合存储，可插拔的 embedder/LLM，附 Neo-Brutalism Web 控制台 | Python 3.11+ · SQLAlchemy 2.0 · FastAPI · Chroma | 98 个测试 · 85 文件 |
| [**ai-travel-assistant**](ai-travel-assistant/) | AI 智行助手：行程规划 + SSE 流式对话，模型自行决定调用高德 / 12306 / 酒店等 MCP 工具 | FastAPI · openai SDK · MiniMax-M3 · MCP | 27 文件 |
| [**travel-assistant-v5**](travel-assistant-v5/) | AI 智行助手 v5：多页版，带**通用 MCP 客户端**（JSON-RPC over HTTP），5 个页面 + 行程历史落盘，含离线 mock MCP server | FastAPI · httpx · PyYAML · 原生前端 | 36 文件 |
| [**private-rag**](private-rag/) | 本地知识库问答：多格式文档入库、带引用来源、非知识类问题自动跳过检索以省 token | FastAPI · FAISS · Qwen3-Embedding-4B · MiniMax-M3 | 22 文件 |
| [**context-pilot**](context-pilot/) | Context Pilot：LLM 上下文管理教学演示 —— KV Cache 命中/未命中、窗口溢出三策略对比、RAG 与工具调用透明化。**演示模式零 API Key 即可完整跑通** | FastAPI · LangChain · FAISS | 21 文件 |
| [**desktop-pet**](desktop-pet/) | Windows 桌面宠物：透明穿透窗口、眼球跟随、摸头爱心、托盘菜单、位置记忆。角色是手绘 SVG，无需 Live2D 素材即可运行 | Electron 31 · TypeScript · electron-builder | 16 文件 |
| [**personal-site**](personal-site/) | 个人主页：科幻 HUD 风格单页站。零依赖零构建，双击 `index.html` 即可打开 | 原生 HTML/CSS/JS | 9 文件 |

另有 [`_archive/`](_archive/)，存放旧版本、第三方素材与历史记录，**不参与发布**，详见其中的 README。

---

## 快速开始

每个项目都是自包含的，进入对应目录按其 `README.md` 操作即可。几个通用的起点：

```bash
# Python 项目（memoria / private-rag / context-pilot / *-travel-assistant）
cd memoria
pip install -e ".[dev]"          # memoria 是标准包，其余用 requirements.txt
cp .env.example .env             # 填入自己的 API Key（模板文件已入库，真实文件被忽略）

# Electron 项目
cd desktop-pet
npm install && npm start
```

> 除 `context-pilot` 的演示模式外，其余项目都需要自备 API Key 才能完整运行。
> 各项目的 `.env.example` / `*.example.json` / `*.example.yaml` 列出了全部配置项。

---

## 目录约定

- **凭据一律不入库**：真实配置文件（`.env`、`data/config.yaml`、`backend/config.json`、
  `data/settings.json`、`secrets.bat`）都被各自的 `.gitignore` 排除，仓库里只保留
  `*.example.*` 模板。
- **构建产物不入库**：`node_modules/`、`release/`、`dist/`、各类缓存目录。
- `_archive/` 不发布。
- 每个项目的 `.gitignore` 独立生效，可单独复制出去作为独立仓库使用。

---

## 安全说明

本仓库中**不包含任何真实密钥**。但如果你是在本地开发这些项目，请注意：
真实凭据存放在被 gitignore 的文件里，仅存在于本机磁盘，请勿手动提交或外传。
若这些 Key 曾经以明文形式共享过，建议到各平台控制台重新生成：

- 高德开放平台 → 应用管理 → 重新生成 Key
- DeepSeek / MiniMax / 硅基流动 / 阿里云百炼 → API Key 管理 → 删除旧 Key 并新建

轮换后把新 Key 填回本地对应文件即可，无需改动任何代码。

---

## License

各项目独立授权，均为 [MIT](LICENSE)。© 2026 zzdjjdd
