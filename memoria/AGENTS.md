# AGENTS.md

Guide for AI coding agents (and human contributors) working in this repository.

## What this project is

**Memoria** is an **embedded memory module** (a Python library) for an Agent application.
It provides short-term + long-term memory using a four-layer cognitive model, backed by a
**hybrid store** (vector DB for semantic recall + relational DB for exact/filtered lookup).

Product requirements and design rationale live in [`docs/PRD.md`](docs/PRD.md) — read it
before significant changes. `CLAUDE.md` holds Claude-Code-specific conventions; this file is
the canonical "how to work in this repo" guide.

## Repository layout

```
memoria/                # Python package
  manager.py            # Memory — the ONLY public facade
  config.py             # Config
  embedders/            # pluggable embedding providers (base / fake / local / openai / factory)
  llms/                 # pluggable LLM providers (base / fake / openai_compat / factory)
  mcp/                  # MCP tool servers (base / remote SSE / fake)
  agent.py              # tool-using conversational agent (memory + LLM + MCP)
  vector/               # pluggable vector stores (base / memory / chroma / factory)
  stores/               # working, episodic, semantic, procedural
  retrieval/            # cross-layer retriever, RRF fusion, strength scoring
  consolidation/        # consolidator (distill / summarize), forgetting (decay)
  db/                   # SQLAlchemy models + session
migrations/             # Alembic migrations (schema changes go here)
tests/                  # pytest
docs/PRD.md             # product doc
pyproject.toml
```

## Build & run

```bash
pip install -e ".[dev]"     # install with dev extras
```

Requires Python 3.11+. The default runtime is fully embedded/offline:
SQLite (structured) + Chroma (vectors) + a local sentence-transformers embedder.

## Testing

```bash
pytest -q                       # full suite — MUST pass offline (no network)
pytest --cov=memoria -q         # with coverage
ruff check memoria tests        # lint
ruff format --check memoria tests
mypy memoria                    # type check
```

Conventions:
- Tests must never hit the real network. Use `FakeEmbedder` (deterministic vectors) and `FakeLLM`.
- DB tests use a throwaway SQLite via `tmp_path`.
- Retrieval tests use a fixed corpus/seed so assertions are reproducible.

## Domain model primer (read before touching memory logic)

Four memory layers — they are **not interchangeable**:

| Layer | Meaning | Persistence | Write API |
| --- | --- | --- | --- |
| **Working** | active context of the current session | in-memory, ephemeral | `mem.working.append(...)` |
| **Episodic** | what happened, when, where | long-term, decays | `mem.remember_event(...)` |
| **Semantic** | distilled stable facts / preferences | long-term, durable | `mem.upsert_fact(...)` |
| **Procedural** | how to do things (skills/workflows) | long-term, reinforced by use | `mem.record_procedure(...)` |

Lifecycle: turns accumulate in Working → flushed/summarized into Episodic →
Consolidator distills stable facts into Semantic/Procedural → Forgetting decays weak memories.
Retrieval pulls across layers and injects the result back into Working context.

**Retrieval score** (default):
```
score = RRF_rank × importance × recency_decay(age) × (1 + log(1 + access_count))
```
`recency_decay` tau differs per layer (episodic decays fast; semantic/procedural slow).

Hard rules:
- Every long-term record carries a `namespace` (isolation key). **All** reads/writes must
  filter by namespace, or data leaks across users/sessions.
- Semantic upserts must dedupe + merge confidence, and keep `source_episode_ids` for traceability.
- A retrieval hit must bump `access_count` / `last_accessed_at` ("used → stronger").

## Code style & conventions

- Python 3.11+, full type annotations, `mypy` clean, `ruff` formatted.
- Public surface goes through the `Memory` facade (`memoria.manager`). Do not export or
  require importing internal store/provider classes.
- Providers (embedder, LLM) and storage engines are dependency-injected behind interfaces.
  Add a new embedder by implementing `memoria/embedders/base.py`.
- Raise typed exceptions from `memoria.errors`; never raise bare `Exception`.

## Database changes

- Structured schema lives in `memoria/db/models.py` (SQLAlchemy).
- Any schema change **must** ship an Alembic migration; never mutate the DB by hand.
  ```bash
  alembic revision --autogenerate -m "describe change"
  alembic upgrade head
  ```

## Security guardrails

- 🔴 Secrets (API keys, passwords) come from environment variables ONLY — never persist them,
  log them, put them in prompts, or commit them.
- 🔴 Sensitive memory fields must be encryptable. The delete API (`delete_where`) exists for
  privacy compliance (right to be forgotten) — do not bypass it.
- 🔴 Don't log raw memory content by default (may contain user PII).

## Common tasks (how-to)

| Task | Do this |
| --- | --- |
| Add a new memory field | edit `db/models.py` + add Alembic migration + update store + tests |
| Add a new embedder | implement `embedders/base.py`, register in `embedders/factory.py`, add a fake-based test |
| Add a new LLM provider | implement `llms/base.py`, register in `llms/factory.py` |
| Add a new vector backend | implement `vector/base.py`, register in `vector/factory.py` |
| Change retrieval ranking | edit `retrieval/scoring.py` + `fusion.py`, update `tests/test_scoring.py` |
| Tune forgetting | adjust per-layer `tau` in `retrieval/scoring.py` and threshold in `store.forget()` |

## Commit & PR conventions

- Conventional Commits: `feat: fix: refactor: test: docs: chore:`.
- One logical change per commit; schema commits must include their migration file.
- PRs must keep `pytest`, `ruff`, and `mypy` green.
