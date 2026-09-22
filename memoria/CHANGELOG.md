# 更新日志（CHANGELOG）

本项目所有重要变更都记录在此文件。
格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/)，版本号遵循语义化版本。

## [0.1.0] - 2026-08-02

首个可用版本：完整的四层记忆内核 + Neo-Brutalism 网页 + FastAPI 真后端。

### 新增 · M0 骨架
- `memoria` Python 包：`Config`、类型化异常、`Memory` 门面（唯一对外入口）。
- 可插拔 Embedder 抽象：`fake`（离线默认）/ `local`（sentence-transformers）/ `openai`，工厂 + 懒加载。
- 可插拔向量存储：`memory`（零依赖）/ `chroma`（持久化）。
- SQLAlchemy 数据模型（episodic / semantic / procedural）+ Alembic 初始迁移。
- pytest 离线测试基座（`DeterministicFakeEmbedder`）+ GitHub Actions CI（ruff + mypy + pytest）。

### 新增 · M1 短期 + 情景记忆
- 工作记忆：滑动窗口 + token 预算（token 计数器可插拔）。
- 情景记忆存取：写入同时落 SQLite + 向量库（同一 id），命中回写 `access_count`。
- 基础向量检索，全程 `namespace` 隔离。

### 新增 · M2 语义 + 程序 + 混合检索
- 语义记忆：upsert 去重、置信度合并、`source_episode_ids` 溯源。
- 程序记忆：成功强化 / 失败降权，重要性随成功次数增长。
- 混合检索：跨层向量召回 → RRF 融合 → 强度重排（重要性 × 时近性 × 频率，分层 tau）。
- `build_context()`：组装可直接注入提示词的上下文（受 token 预算约束）。

### 新增 · M3 巩固 + 遗忘
- 巩固：情景→语义事实蒸馏（抽取器可插拔，默认启发式）、工作→情景摘要。
- 遗忘：强度衰减 + 容量淘汰，向量同步删除（程序记忆由强化机制管理，不参与衰减）。

### 新增 · M4 治理 + 评估
- `stats()`：各层计数 + 召回命中率（可观测性）。
- `export()`：整命名空间导出 JSON（可写入文件）。
- `delete_where()`：定向删除 / 被遗忘权（无条件 = 清空命名空间），同步删向量。
- `memoria.evaluation.evaluate_recall()`：召回质量评估 harness（hit-rate@k）。

### 新增 · 真实模型接入（可插拔）
- Embedding：`OpenAIEmbedder` 支持任意 OpenAI 兼容端点与 `dimensions` 参数，可接
  千问 `text-embedding-v3`（DashScope 兼容端点）；凭据走 `EMBEDDER_API_KEY` /
  `EMBEDDER_BASE_URL` 环境变量，绝不落库。
- LLM：新增 `memoria/llms`（base / fake / openai_compat / factory），可接 DeepSeek
  `deepseek-v4-flash`；用于巩固阶段的事实蒸馏与对话摘要，失败自动回退启发式。
- `Config` 新增 `llm_model` / `llm_base_url` / `embedder_dimensions`。
- Web 后端新增对应环境变量（`MEMORIA_LLM*`、`MEMORIA_EMBEDDER_MODEL` 等）。

### 新增 · 工具调用 / MCP（Phase 2）
- `memoria/mcp`：MCP 工具服务器抽象（SSE 远程 + 离线 Fake），默认接高德托管端点
  `https://mcp.amap.com/sse?key=...`（地理编码 / POI 周边搜索 / 路径规划 / 天气 / 距离）。
- LLM 增加 `chat_with_tools`（OpenAI 兼容 function calling，适用于 DeepSeek）。
- `memoria/agent.py`：Agent 工具循环——召回记忆 → LLM 决策 → 调工具 → 回填结果 → 回复 → 沉淀。
- Web：`/api/chat` 改走 Agent（async），新增 `/api/tools`；控制台展示本轮调用了哪些工具。
- 依赖：`pip install mcp`（已加入 `web` extra）。

### 新增 · 记忆对话（Phase 1）
- LLM 抽象增加多轮 `chat`；`Memory.chat()`：召回相关长期记忆 → 注入提示词 →
  LLM 回复 → 存入情景并增量蒸馏事实（越聊越懂你）。
- 巩固改为增量蒸馏：只处理新增情景，避免重复调用 LLM。
- Web 控制台升级为 Neo-Brutalism 聊天界面（气泡 + 四层记忆格），新增 `POST /api/chat`；
  保持双模式（真实后端 / 本地演示）。

### 新增 · Web
- `web/index.html`：Neo-Brutalism 单页（粗描边 / 糖果色 / 平移阴影 / 贴纸 / 噪点背景），
  内置「记忆控制台」——双模式：连得上后端用真实数据（徽标「● 真实后端」），否则本地演示回退。
- `web/app.py`：FastAPI 暴露 `health / dump / remember / recall / procedure /
  forget / flush / stats / export / delete` + Swagger（`/docs`）。
- `start.bat`：UTF-8 一键启动脚本（自动打开浏览器）。

### 修复
- `make_engine`：`sqlite:///:memory:` 在多线程（FastAPI 线程池）下改用 `StaticPool`
  共享单连接，修复「启动时建表、请求线程却看不到表（no such table）」的问题。

### 使用说明
- 默认演示后端为进程内存储（重启即清空）。
- 持久化：设 `MEMORIA_SQLITE_URL`（文件）+ `MEMORIA_VECTOR_STORE=chroma`（需 `pip install memoria[vector]`）。
- 真实语义召回：设 `MEMORIA_EMBEDDER=local` 或 `openai`（默认 `fake` 仅用于离线演示）。
