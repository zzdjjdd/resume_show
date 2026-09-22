# Memoria 记忆系统 · 产品需求文档（PRD）

| 字段 | 内容 |
| --- | --- |
| 产品代号 | Memoria |
| 文档版本 | v0.1（草案） |
| 日期 | 2026-08-01 |
| 产品形态 | 某 Agent 应用的**内置记忆模块**（Python 库） |
| 技术栈 | Python |
| 记忆模型 | 工作记忆 / 情景记忆 / 语义记忆 / 程序记忆（四层认知模型） |
| 存储方案 | 混合：向量库（语义召回）+ 结构化库（精确查询/过滤） |

---

## 1. 背景与目标

### 1.1 问题
当前 Agent 应用只有"金鱼记忆"：上下文窗口一满就丢失历史信息，无法跨会话记住用户偏好、既往事实和习得的操作流程。这导致：
- 重复询问用户已经说过的事情；
- 无法积累对用户的理解，个性化能力弱；
- 多轮/多会话任务缺乏连续性。

### 1.2 目标
为 Agent 应用提供一个**内置的、可演进的短期 + 长期记忆系统**：
- **短期记忆**：在单次会话内维持连贯的上下文（工作记忆）。
- **长期记忆**：跨会话持久化"发生过什么（情景）""知道什么（语义）""会做什么（程序）"。
- **自动沉淀**：把短期/情景记忆自动提炼、巩固为长期记忆，并按重要性衰减遗忘。

### 1.3 非目标（本期不做）
- ❌ 独立对外提供 SaaS / 多租户云服务（本期仅作为内置模块；预留 namespace 隔离以便未来扩展）。
- ❌ 复杂的知识图谱推理（保留为未来演进方向，见 §11）。
- ❌ 记忆的多 Agent 共享/联邦（预留接口，不在本期实现）。

---

## 2. 名词与记忆分层模型

借鉴认知科学，记忆分为四层。**这是全系统的核心数据模型，所有模块围绕它组织。**

| 层级 | 英文 | 是什么 | 生命周期 | 存储 | 典型内容 |
| --- | --- | --- | --- | --- | --- |
| **工作记忆** | Working Memory | 当前会话的活跃上下文 | 会话级（进程内，易失） | 内存环形缓冲 | 最近 N 轮对话、当前任务状态 |
| **情景记忆** | Episodic | "何时何地发生了什么" | 长期，可衰减 | 结构化 + 向量 | "2026-08-01 用户让我重构了登录模块" |
| **语义记忆** | Semantic | 提炼出的稳定事实/知识/偏好 | 长期，高持久 | 结构化 + 向量 | "用户偏好深色主题""项目用 Python" |
| **程序记忆** | Procedural | "如何做某事"的技能/流程 | 长期，按使用强化 | 结构化 + 向量 | "部署前先跑测试""用户习惯的提交规范" |

**记忆生命周期**（核心闭环）：

```
        写入/编码               巩固(consolidate)            衰减/遗忘
对话 ─────────────▶ 工作记忆 ──────────────▶ 情景记忆 ──────────────▶ (淘汰)
                       │                       │  提炼事实
                       │ 会话结束/滚动摘要       ▼
                       └──────────────────▶ 语义记忆 / 程序记忆（长期沉淀）

检索(retrieve)：工作记忆发起 ──▶ 跨层混合召回 ──▶ 融合打分 ──▶ 注入回工作记忆上下文
```

---

## 3. 用户场景 / 用例

| # | 场景 | 涉及层级 | 期望行为 |
| --- | --- | --- | --- |
| U1 | 跨会话记住偏好 | 语义 | 上周用户说"我喜欢深色主题"，本周新会话 Agent 主动沿用，无需再问。 |
| U2 | 会话内连贯追问 | 工作 | 用户连续追问"那它呢？""再详细点"，Agent 知道"它"指代上一轮的对象。 |
| U3 | 回忆既往事件 | 情景 | "我们上次讨论的那个方案是什么？" → 按语义+时间召回相关事件。 |
| U4 | 复用习得流程 | 程序 | 用户多次要求"提交前跑测试"，系统沉淀为程序记忆，之后自动遵循。 |
| U5 | 重要性遗忘 | 全层 | 半年前的琐碎闲聊被衰减淘汰，重要事件长期保留。 |
| U6 | 隐私删除 | 全层 | 用户要求"忘掉我所有的银行卡信息" → 定向删除相关记忆并可导出。 |

---

## 4. 功能需求

### 4.1 写入（Encode）
- **FR-1** 工作记忆追加：支持按轮次追加消息，维护滑动窗口与 token 预算。
- **FR-2** 事件记录：将一次交互/事件写入情景记忆，自动打时间戳、生成 embedding、可附 importance 与 metadata。
- **FR-3** 事实 Upsert：写入/更新语义记忆（subject + fact + confidence），相同事实做去重与置信度合并。
- **FR-4** 程序记录：记录"触发条件 → 步骤"的程序记忆，记录成功/失败次数。

### 4.2 检索（Retrieve）
- **FR-5** 跨层检索：一次查询可同时召回情景/语义/程序记忆。
- **FR-6** 混合召回：向量语义召回 + 结构化过滤（时间范围、类型、namespace、metadata）并行。
- **FR-7** 融合打分：用 RRF（Reciprocal Rank Fusion）融合多路结果，并叠加 **重要性 × 时近性 × 访问频率** 加权（见 §6.3）。
- **FR-8** 可选重排：支持 LLM/交叉编码器对 top-k 重排（可关闭以省成本）。
- **FR-9** 上下文组装：`build_context(token_budget)` 把召回结果 + 工作记忆拼成可直接注入提示词的文本，受 token 预算约束。

### 4.3 巩固与遗忘（Consolidate / Forget）
- **FR-10** 情景→语义提炼：周期性从情景记忆中抽取稳定事实，沉淀为语义记忆（LLM 辅助，可规则兜底）。
- **FR-11** 工作→情景摘要：会话结束或窗口溢出时，将工作记忆压缩为情景摘要。
- **FR-12** 衰减/遗忘：按重要性×时近性×频率计算记忆强度，低于阈值或超过容量上限的记忆被归档/删除。
- **FR-13** 程序强化：程序记忆被成功使用则强化，反复失败则降权。

### 4.4 管理与治理
- **FR-14** 命名空间隔离：支持 `namespace`（如 user_id / session_id）隔离，保证多用户/多会话不串扰。
- **FR-15** 可观测：暴露统计（各层记忆条数、召回命中率、token 用量）。
- **FR-16** 可删除/可导出：支持按条件删除（right to be forgotten）与导出（JSON），满足隐私合规。

---

## 5. 非功能需求

| 类别 | 指标 |
| --- | --- |
| 性能 | 单条检索 P95 < 200ms（单机、≤10 万条记忆）；写入 P95 < 100ms |
| 容量 | 单实例支撑 10 万级记忆条目；超出时优先触发遗忘而非报错 |
| 可用性 | 嵌入式、零外部服务依赖即可运行（SQLite + 本地 embedding） |
| 可测试 | Embedder / LLM 均可被 mock，核心逻辑单测可在无网络下运行 |
| 隐私安全 | 敏感字段可加密存储；API Key 只从环境变量读取，绝不落库/入提示词 |
| 可扩展 | 存储引擎、embedding、LLM 均为可插拔接口，替换不改业务代码 |
| 可迁移 | 结构化 schema 变更走迁移工具（Alembic），禁止手改库 |

---

## 6. 系统架构

### 6.1 组件图

```
                        ┌──────────────────────────────────────────┐
   Agent 应用  ───────▶│            Memory（门面 / Facade）          │
                        └───────┬───────────────────────────────┬───┘
                ┌───────────────┼───────────────┬───────────────┼────────────┐
                ▼               ▼               ▼               ▼            ▼
        WorkingMemory     EpisodicStore   SemanticStore   ProceduralStore  Retriever
        (内存环形缓冲)      (结构化+向量)    (结构化+向量)    (结构化+向量)    (混合召回+融合)
                │               │               ▲               │            │
                │               │   提炼事实      │               │            │
                │          Consolidator ─────────┘   Forgetting(衰减)          │
                └───────────────┴───────┬──────────────┴──────────────────────┘
                                        ▼
                     ┌─────────────────────────────────────┐
                     │  基础设施：Embedder / LLM / DB 会话    │
                     │  SQLite(SQLAlchemy) + Chroma(向量)    │
                     └─────────────────────────────────────┘
```

### 6.2 数据流
1. **回合开始**：Agent 调 `recall(query)` → Retriever 跨层混合召回 → `build_context()` 注入工作记忆。
2. **回合进行**：消息追加进 WorkingMemory（滑动窗口 + token 预算）。
3. **回合/会话结束**：触发 `consolidate()` → 工作记忆摘要进情景、情景提炼进语义/程序。
4. **周期任务**：`forgetting` 衰减低强度记忆；`retrieval` 命中会反向提升记忆强度（越用越牢）。

### 6.3 检索打分公式（推荐默认）
单条记忆最终得分：

```
score = RRF_rank_score                          # 多路召回的名次融合
        × importance                            # 写入时的重要性 [0,1]
        × recency_decay(age)                    # recency = exp(-age_hours / tau)，tau 可配
        × (1 + log(1 + access_count))           # 访问频率加成
```

- `RRF_rank_score = Σ 1 / (k + rank_i)`，k 默认 60。
- `recency_decay` 对情景记忆敏感，对语义/程序记忆衰减更慢（分层 tau）。

### 6.4 目录结构（目标形态）

```
memoria/                      # Python 包
  __init__.py                 # 导出 Memory, Config
  config.py                   # 配置（dataclass / pydantic）
  manager.py                  # Memory 门面，对外唯一入口
  embedders/
    base.py                   # Embedder 抽象接口
    local.py                  # sentence-transformers（默认，离线）
    openai.py                 # OpenAI / 兼容 API（可插拔）
  stores/
    working.py                # 工作记忆（内存）
    episodic.py               # 情景记忆
    semantic.py               # 语义记忆
    procedural.py             # 程序记忆
  retrieval/
    retriever.py              # 跨层检索编排
    fusion.py                 # RRF 融合
    scoring.py                # 重要性×时近×频率
  consolidation/
    consolidator.py           # 情景→语义提炼、工作→情景摘要
    forgetting.py             # 衰减与淘汰
  db/
    models.py                 # SQLAlchemy ORM
    session.py                # 连接/会话管理
migrations/                   # Alembic 迁移
tests/                        # pytest
docs/PRD.md
pyproject.toml
```

---

## 7. 数据模型（结构化表，SQLite）

> 向量存于 Chroma，以下为主存于 SQLite 的结构化字段；每条长期记忆在 Chroma 中有对应 embedding，以 `id` 关联。

**episodic_memory（情景）**
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | TEXT PK | UUID |
| namespace | TEXT | 隔离键（user/tenant） |
| session_id | TEXT | 所属会话 |
| content | TEXT | 事件内容 |
| importance | REAL | 重要性 [0,1] |
| access_count | INT | 命中次数 |
| last_accessed_at | DATETIME | 最近命中时间 |
| created_at | DATETIME | 事件时间 |
| metadata | JSON | 扩展字段 |

**semantic_memory（语义）**
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | TEXT PK | UUID |
| namespace | TEXT | 隔离键 |
| subject | TEXT | 主体（如 "user"） |
| fact | TEXT | 事实/偏好陈述 |
| confidence | REAL | 置信度 [0,1] |
| source_episode_ids | JSON | 来源情景 id 列表（可溯源） |
| access_count / last_accessed_at / created_at / updated_at | … | 同上 |

**procedural_memory（程序）**
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | TEXT PK | UUID |
| namespace | TEXT | 隔离键 |
| trigger | TEXT | 触发条件描述 |
| steps | JSON | 步骤列表 |
| success_count / failure_count | INT | 强化/降权依据 |
| last_used_at / created_at | DATETIME | … |

> 工作记忆不落库（进程内），仅随会话存在。

---

## 8. 对外接口设计（Python API 草案）

```python
from memoria import Memory, Config

mem = Memory(Config(
    sqlite_url="sqlite:///./memoria.db",
    chroma_path="./.chroma",
    embedder="local",              # 或 "openai"
    namespace="user:123",
))

# ── 写入 ──
mem.working.append(role="user", content="帮我把登录模块重构成 async")
mem.remember_event(content="重构了登录模块为 async", importance=0.7,
                   metadata={"module": "auth"})
mem.upsert_fact(subject="user", fact="偏好深色主题", confidence=0.9)
mem.record_procedure(trigger="部署生产环境",
                     steps=["跑测试", "构建", "灰度发布"])

# ── 检索（跨层混合召回）──
hits = mem.recall(
    query="用户的界面偏好",
    layers=["semantic", "episodic", "procedural"],
    top_k=5,
    filters={"created_after": "2026-01-01"},
)

# ── 巩固 / 遗忘（通常后台周期触发）──
mem.consolidate()      # 情景→语义提炼、工作→情景摘要
mem.forget()           # 衰减并淘汰低强度记忆

# ── 组装注入提示词的上下文 ──
ctx: str = mem.build_context(token_budget=1500)

# ── 治理 ──
mem.export("backup.json")
mem.delete_where(subject="user", fact_contains="银行卡")   # right to be forgotten
```

**设计原则**：`Memory` 是唯一对外门面；所有 provider（embedder/llm）与存储引擎均依赖注入，便于测试替换。

---

## 9. 关键决策记录（ADR 摘要）

| # | 决策点 | 已选方案 | 主要备选 | 选择理由 |
| --- | --- | --- | --- | --- |
| ADR-1 | 产品形态 | **内置模块** | 独立服务/MCP Server、SDK | 贴合单一 Agent 应用，调用零网络开销；用 namespace 预留未来拆分空间 |
| ADR-2 | 记忆分层 | **四层认知模型**（工作/情景/语义/程序） | 两层（短期+长期）、三层（缓冲+摘要+知识） | 表达力最强，贴合认知科学，检索/遗忘可分层差异化 |
| ADR-3 | 存储检索 | **向量库 + 结构化库 混合** | 纯向量、纯文件、知识图谱 | 兼顾语义召回与精确/时间/结构化过滤，召回质量与可控性最佳 |
| ADR-4 | 技术栈 | **Python** | TypeScript、双栈 | AI/向量/记忆生态最成熟，资料最丰富 |
| ADR-5 | 默认存储引擎 | **SQLite（结构化）+ 可插拔向量存储**（默认 `InMemory` 离线、生产切 `Chroma`） | sqlite-vec、PGVector、Qdrant | 向量后端经 factory 可插拔：默认零依赖、可离线测试；生产用 Chroma 持久化；规模化后可平滑换 PGVector |
| ADR-6 | 检索融合 | **RRF + 重要性×时近×频率加权** | 单一相似度、纯 LLM 重排 | 无需调权重的稳健融合，成本低；LLM 重排作为可选增强 |
| ADR-7 | 遗忘策略 | **强度 = 重要性×时近×频率，阈值淘汰** | 仅按时间 FIFO、永不删除 | 模拟人脑"越重要/越常用越牢"，控制容量 |

---

## 10. 里程碑 / 迭代计划

| 里程碑 | 交付内容 | 验收 |
| --- | --- | --- |
| **M0 骨架** | 项目脚手架、Config、Embedder 抽象、CI、pytest 基座 | `pip install -e .` 成功；空测试通过 |
| **M1 短期+情景** ✅ | WorkingMemory（滑动窗口/token 预算）、EpisodicStore 存取、基础向量检索 | U2、U3 可跑通 |
| **M2 语义+程序+混合检索** ✅ | Semantic/ProceduralStore、Retriever、RRF 融合、打分、`build_context` | U1、U4 可跑通；检索 P95 达标 |
| **M3 巩固+遗忘** ✅ | Consolidator（情景→语义、工作→情景）、Forgetting、程序强化 | U5 可跑通；容量超限时自动遗忘 |
| **M4 治理+评估** ✅ | namespace 隔离、导出/删除、可观测指标、召回命中率评估集 | U6 可跑通；有评估报告 |

---

## 11. 风险与开放问题

| 风险/问题 | 影响 | 缓解 / 待决策 |
| --- | --- | --- |
| LLM 提炼事实可能引入错误记忆 | 语义记忆失真 | 保留 `source_episode_ids` 溯源；置信度阈值；人工可纠正 |
| embedding 模型中英文效果差异 | 中文召回质量 | 默认用多语言/bge 类模型；embedding 可插拔 |
| 记忆无限增长 | 存储/检索变慢 | 遗忘策略 + 容量上限触发淘汰（FR-12） |
| 隐私合规 | 法律风险 | 敏感字段加密、可删除、可导出（FR-16） |
| 是否引入知识图谱增强语义记忆 | 关联推理能力 | 本期不做；语义记忆 `source_episode_ids` 已为图化留口 |
| embedding/LLM 成本 | 运行成本 | 默认本地 embedding；LLM 仅用于巩固/重排，可关 |

---

## 12. 关键后续决策（已定 / 待定）
1. **向量引擎** ✅：默认 `InMemory`（离线）+ `Chroma`（生产），经 factory 可插拔。
2. **embedding 模型** ✅：接千问 `text-embedding-v3`（OpenAI 兼容端点；`embedder="openai"` + `EMBEDDER_BASE_URL`）。
3. **LLM 模型** ✅：接 `deepseek-v4-flash`（`llm="deepseek"`），用于巩固阶段事实蒸馏与对话摘要，失败回退启发式。
4. **巩固触发方式**（当前同步手动 `consolidate()` / `flush_working()`）：是否加异步后台周期任务，待定。
5. **LLM 重排**：默认关（可选增强），待定。
