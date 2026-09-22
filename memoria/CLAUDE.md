# CLAUDE.md

本文件为 Claude Code 在本仓库（**Memoria** 记忆系统）工作时提供指引。
通用的构建/测试/代码规范见 `AGENTS.md`；本文件聚焦 Claude Code 需要的约定与领域知识。

## 项目一句话

Memoria 是某 Agent 应用的**内置记忆模块**（Python 库），实现短期 + 长期记忆，采用
**工作记忆 / 情景 / 语义 / 程序** 四层认知模型，存储为 **向量库 + 结构化库** 混合。

## 常用命令

```bash
# 安装（开发模式）
pip install -e ".[dev]"

# 测试（核心逻辑必须可在无网络下运行 —— embedder/llm 均 mock）
pytest -q
pytest tests/test_retriever.py -q          # 单文件
pytest -k "recall" -q                       # 按名字筛选
pytest --cov=memoria                        # 覆盖率

# 静态检查 / 格式化
ruff check memoria tests
ruff format memoria tests
mypy memoria

# 数据库迁移（结构化 schema 变更必须走迁移，禁止手改库）
alembic revision --autogenerate -m "add xxx"
alembic upgrade head
```

## 架构速览

```
Memory(门面, manager.py) ── 唯一对外入口
  ├─ WorkingMemory ✅   滑动窗口 + token 预算（会话级，不落库）
  ├─ EpisodicStore ✅   情景：何时何地发生了什么（SQLite + 向量）
  ├─ SemanticStore ✅   语义：去重 + 置信度合并 + 溯源
  ├─ ProceduralStore ✅ 程序：成功强化 / 失败降权
  ├─ Retriever ✅       跨层召回 → RRF 融合 → 强度重排
  ├─ Consolidator ✅    情景→语义蒸馏、工作→情景摘要
  ├─ Forgetting ✅      强度衰减 + 容量淘汰
  ├─ Agent ✅          工具型对话：记忆召回 + LLM 决策 + MCP 工具调用
  └─ MCP ✅            外接工具服务（高德地图：地理编码/POI/路径/天气）
基础设施：Embedder(可插拔:fake/local/openai兼容千问) / LLM(可插拔:fake/deepseek/openai,对话+巩固+工具决策) / VectorStore(memory/chroma) / MCP(高德SSE) / SQLite(SQLAlchemy)
```

- 结构化表：SQLite（SQLAlchemy ORM，见 `memoria/db/models.py`）。
- 向量：经 `memoria/vector/factory.py` 可插拔——默认 `memory`（零依赖、离线），
  生产切 `chroma`（持久化，`Config.chroma_path`）。与结构化记录以同一 `id` 关联。
- `Memory` 是对外**唯一门面**；provider 与存储引擎一律依赖注入。

## 领域约定（改代码前务必理解）

四层记忆语义不同，**不要把语义记忆当情景记忆用**：

| 层 | 写入入口 | 关键特征 |
| --- | --- | --- |
| 工作记忆 | `mem.working.append(...)` | 易失、滑动窗口 + token 预算 |
| 情景 | `mem.remember_event(...)` | 带时间戳、importance、可衰减 |
| 语义 | `mem.upsert_fact(...)` | 稳定事实，需去重 + 置信度合并，保留 `source_episode_ids` 溯源 |
| 程序 | `mem.record_procedure(...)` | `trigger→steps`，按 success/failure 强化/降权 |

- **检索打分**：`score = RRF × importance × recency_decay(age) × (1+log(1+access_count))`，
  衰减系数 `tau` 分层不同（情景快、语义/程序慢）。改打分逻辑时同步更新 `tests/test_scoring.py`。
- 所有长期记忆都带 `namespace`（隔离键）。任何存储/查询都**必须**带 namespace 过滤，否则会串扰。
- 命中检索要回写 `access_count` / `last_accessed_at`（越用越牢），别漏。

## 编码规范（摘要）

- Python 3.11+，类型注解齐全，`mypy` 通过。
- 对外 API 走 `Memory` 门面，不要让用户直接 import 子模块内部类。
- 新增长期记忆字段 → 改 `db/models.py` **并** 生成 Alembic 迁移。
- 抽象优先：embedding / LLM / 存储都通过接口注入；新增 provider 实现 `embedders/base.py` 的接口。
- 错误用自定义异常（`memoria.errors`），不要裸抛 `Exception`。

## 测试约定

- 单测**禁止真实网络调用**：用 `FakeEmbedder`（确定性向量）与 `FakeLLM`。
- 检索类测试用固定种子/固定语料，断言可复现。
- 涉及 DB 的测试用临时 SQLite（`tmp_path`），不污染真实库。

## 安全 / 红线

- 🔴 **API Key、密码等机密只从环境变量读**，绝不写入库、日志、提示词或提交到 git。
- 🔴 敏感记忆字段需可加密；删除接口（`delete_where`）是合规需求，不要为了省事绕过。
- 🔴 不要把记忆原文无条件塞进日志（可能含用户隐私）。

## 提交规范

- Conventional Commits：`feat:` / `fix:` / `refactor:` / `test:` / `docs:` / `chore:`。
- 一个提交一件事；改 schema 的提交必须附带迁移文件。
