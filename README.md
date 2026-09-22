# 项目集 · Projects

这里是我的个人项目集合。每个子目录都是一个**独立的 git 仓库**（各自有 `.git`、
`README.md`、`LICENSE`、`.gitignore`），可以单独推送到 GitHub。

---

## 项目一览

| 项目 | 是什么 | 技术栈 | 规模 |
|---|---|---|---|
| [**memoria**](memoria/) | Agent 的短期 + 长期记忆模块：四层认知模型（工作/情景/语义/程序），向量库 + SQLite 混合存储，可插拔的 embedder/LLM，附 Neo-Brutalism Web 控制台 | Python 3.11+ · SQLAlchemy 2.0 · FastAPI · Chroma | 98 个测试 · 85 文件 |
| [**desktop-pet**](desktop-pet/) | Windows 桌面宠物：透明穿透窗口、眼球跟随、摸头爱心、托盘菜单、位置记忆。角色是手绘 SVG，无需 Live2D 素材即可运行，已打包出安装版与便携版 exe | Electron 31 · TypeScript · electron-builder | 16 文件 |
| [**ai-travel-assistant**](ai-travel-assistant/) | AI 智行助手（V2）：行程规划 + SSE 流式对话，模型自行决定调用高德 / 12306 / 酒店等 MCP 工具 | FastAPI · openai SDK · MiniMax-M3 · MCP | 27 文件 |
| [**travel-assistant-v5**](travel-assistant-v5/) | AI 智行助手 v5：多页版，带**通用 MCP 客户端**（JSON-RPC over HTTP），5 个页面 + 行程历史落盘，含离线 mock MCP server | FastAPI · httpx · PyYAML · 原生前端 | 36 文件 |
| [**context-pilot**](context-pilot/) | Context Pilot：LLM 上下文管理教学演示 —— KV Cache 命中/未命中、窗口溢出三策略对比、RAG 与工具调用透明化。**演示模式零 API Key 即可完整跑通** | FastAPI · LangChain · FAISS | 21 文件 |
| [**private-rag**](private-rag/) | 本地知识库问答：多格式文档入库、带引用来源、非知识类问题自动跳过检索以省 token | FastAPI · FAISS · Qwen3-Embedding-4B · MiniMax-M3 | 22 文件 |
| [**personal-site**](personal-site/) | 个人主页：科幻 HUD 风格单页站，含技术方向、开源项目、Kaggle 战绩、学术荣誉与技术栈。零依赖零构建，双击 `index.html` 即可打开 | 原生 HTML/CSS/JS | 9 文件 |

另有 [`_archive/`](_archive/)，存放旧版本与第三方素材，**不参与发布**，详见其中的 README。

---

## 推送到 GitHub

每个项目都是独立仓库，已在 `main` 分支完成首次提交。以 `memoria` 为例：

```bash
cd memoria

# 1) 在 GitHub 网页上新建一个空仓库（不要勾选 Add README / .gitignore / license）

# 2) 关联并推送
git remote add origin https://github.com/<你的用户名>/memoria.git
git push -u origin main
```

其余项目同理，把 `memoria` 换成对应目录名即可。仓库名建议与目录名一致：

```
memoria  desktop-pet  ai-travel-assistant  travel-assistant-v5
context-pilot  private-rag  personal-site
```

> 如果用的是 SSH，把 URL 换成 `git@github.com:<你的用户名>/memoria.git`。

### 推送前请确认

- [ ] **轮换所有 API Key**（见下方「安全」）
- [ ] 把 `zzdjjdd` 改成你的真实 GitHub 用户名 —— 出现在三处：
      README 徽章、`desktop-pet/package.json` 的 `repository`、
      以及 `personal-site/index.html` 里 4 个项目卡片的 GitHub 链接
- [ ] `personal-site` 的姓名目前是 **ZZD**，需在 `index.html`（4 处）与
      `script.js`（开机日志）中替换为真实姓名

- [ ] `memoria` 推上去后，可在 README 顶部加回 CI 徽章：
      `![CI](https://github.com/<用户名>/memoria/actions/workflows/ci.yml/badge.svg)`

---

## 安全

**以下 6 个文件曾以明文存放真实 API Key。这些 Key 应当视为已泄露，请全部轮换：**

| 文件 | 涉及的服务 |
|---|---|
| `travel-assistant-v5/data/config.yaml` | DeepSeek · 高德 · ModelScope MCP |
| `ai-travel-assistant/backend/config.json` | MiniMax · 高德 · ModelScope MCP |
| `context-pilot/data/settings.json` | DeepSeek · 阿里云百炼 Embedding · ModelScope MCP |
| `private-rag/.env` | 硅基流动 · MiniMax |
| `memoria/secrets.bat` | 阿里云 DashScope · DeepSeek · 高德 |
| `_archive/travel-assistant-v1/data/config.yaml` | （已清空为占位符） |

这些文件现在都已被各自的 `.gitignore` 排除，**不会进入 git**；密钥仍保留在本地磁盘上，
所以项目照常能跑。但既然它们曾以明文形式存在（且出现在聊天记录 / 备份中），
建议去各平台控制台重新生成：

- 高德开放平台 → 应用管理 → 重新生成 Key
- DeepSeek / MiniMax / 硅基流动 / 阿里云百炼 → API Key 管理 → 删除旧 Key 并新建

轮换后，把新 Key 填回上表对应文件即可，无需改动任何代码。

---

## 目录约定

- 每个项目自成一个仓库，互不依赖，可单独发布。
- 凭据一律走 `.env` 或 `*.example.*` 模板：真实文件被 gitignore，模板文件入库。
- 构建产物（`node_modules/`、`release/`、`dist/`、各类缓存）不入库。
- `_archive/` 不发布。
