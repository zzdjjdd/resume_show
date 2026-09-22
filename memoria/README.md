# Memoria

Embedded **short-term + long-term memory** module for an agent application.

[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-98%20passing-brightgreen)](tests/)

- **Four-layer cognitive model**: working / episodic / semantic / procedural.
- **Hybrid store**: vector DB (semantic recall) + SQLite (exact / filtered lookup).
- **Pluggable providers**: embedder and LLM are swappable via config — no business
  code changes when you change models.
- **Offline by default**: ships with a deterministic fake embedder so the whole
  test suite runs with no network and no heavy dependencies.

> Status: **M0–M4 complete** — all four memory layers, hybrid cross-layer
> retrieval (RRF + strength re-rank), consolidation, forgetting, and governance
> (stats / export / right-to-be-forgotten delete / recall evaluation). A
> Neo-Brutalism web UI ([`web/`](web/)) is wired to a live FastAPI backend;
> double-click `start.bat` to launch. See [`docs/PRD.md`](docs/PRD.md) and
> [`CHANGELOG.md`](CHANGELOG.md).

## Install

```bash
pip install -e ".[dev]"          # library + tests/lint/type-check
pip install -e ".[web,vector]"   # add the FastAPI console and Chroma persistence
```

## Configuration

Every credential is read from the environment — nothing is stored in code or in
the database. Copy the template and fill in your keys:

```bash
cp .env.example .env       # Git Bash / macOS / Linux
copy .env.example .env     # Windows CMD
```

`.env` is gitignored. The web layer loads it automatically when `python-dotenv`
is installed (it ships with the `web` extra); the library itself only reads the
process environment, so any injection method works. See
[`.env.example`](.env.example) for the full list of variables, and
[Swapping the embedder / LLM](#swapping-the-embedder--llm) for per-provider
details. On Windows you can instead keep a `secrets.bat` (also gitignored) —
`start.bat` sources it automatically when present.

## Quick start

```python
from memoria import Config, Memory

mem = Memory(Config(namespace="user:123", embedder="fake"))  # swap to "local"/"openai"
mem.init_db()  # tests/dev convenience; production uses Alembic

# short-term: sliding-window working memory
mem.working.append("user", "I prefer dark themes")

# long-term: episodic memory + hybrid cross-layer retrieval
eid = mem.remember_event("user said they prefer dark themes", importance=0.8)
mem.consolidate()  # distill stable facts into semantic memory
hits = mem.recall("what theme does the user like?")
print(hits[0].content, round(hits[0].score, 4))

# conversation: recall -> inject -> LLM reply -> consolidate
print(mem.chat("what theme do I like?")["reply"])  # needs an LLM configured
```

## Common commands

```bash
pytest -q                       # offline test suite
ruff check memoria tests        # lint
mypy memoria                    # type check
alembic upgrade head            # apply migrations
alembic revision --autogenerate -m "describe change"   # after editing models
```

## Running the web UI

The Neo-Brutalism page in [`web/`](web/) is a live console. Open
`web/index.html` directly and it runs in **demo mode** (client-side
simulation). To drive it with the **real memory backend**:

```bash
pip install -e ".[web]"
python -m uvicorn web.app:app --reload
# open http://127.0.0.1:8000  (the console badge flips to "真实后端")
```

The FastAPI layer (`web/app.py`) exposes `POST /api/chat` (memory-augmented
conversation), `GET /api/dump`, `POST /api/remember`, `POST /api/recall`,
`POST /api/procedure`, `POST /api/forget`, `POST /api/flush`, `GET /api/stats`,
`GET /api/export`, `POST /api/delete`, plus Swagger docs at `/docs`. By default it uses in-process stores (a clean demo
per run); set `MEMORIA_SQLITE_URL` (file) + `MEMORIA_VECTOR_STORE=chroma` for
durable memory, and `MEMORIA_EMBEDDER=local`/`openai` for real semantics.

## Swapping the embedder / LLM

Both are pluggable and OpenAI-compatible. Heavy backends import lazily, so the
default install stays light. Credentials always come from environment variables
— never stored in code or the database.

**Embedding** (`memoria/embedders/factory.py`): `"fake"` (offline default) |
`"local"` (sentence-transformers) | `"openai"` (also any OpenAI-compatible
endpoint, e.g. Qwen). Example — Qwen `text-embedding-v3` via DashScope:

```python
mem = Memory(Config(
    embedder="openai",
    embedder_model="text-embedding-v3",
    embedder_dimensions=1024,
))
# env: EMBEDDER_API_KEY=<DashScope key>
#      EMBEDDER_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

**LLM** (`memoria/llms/factory.py`): `"fake"` | `"deepseek"` / `"openai"` /
`"openai-compat"`, used by consolidation (fact distillation + session
summaries, with heuristic fallback). Example — DeepSeek:

```python
mem = Memory(Config(llm="deepseek", llm_model="deepseek-v4-flash"))
# env: LLM_API_KEY=<DeepSeek key>   (LLM_BASE_URL optional)
```

For the web backend the same settings come from env vars — `MEMORIA_EMBEDDER`,
`MEMORIA_EMBEDDER_MODEL`, `MEMORIA_EMBEDDER_DIMENSIONS`, `MEMORIA_LLM`,
`MEMORIA_LLM_MODEL`, `MEMORIA_LLM_BASE_URL` (see `web/app.py`).

## Tools via MCP (AMap / Gaode Maps)

The agent can call external tools through the Model Context Protocol. Out of the
box it connects to the hosted **AMap MCP** endpoint — geocoding, POI / nearby
search (hotel & place recommendations), route planning (walk / bike / drive /
transit), weather and distance. Set your AMap key and the server connects on
startup (put it in `.env`, or in `secrets.bat` on Windows):

```
set AMAP_MAPS_API_KEY=<your key>
```

or point at any MCP endpoint via `MEMORIA_AMAP_MCP_URL=https://...`. Then ask
things like “北京南站附近有什么酒店” or “从国贸到西单怎么走” — the model decides
which tool to call, and the console shows which tools were used. Requires
`pip install mcp` (included in the `web` extra).

## Swapping the vector store

The vector backend is pluggable too (`memoria/vector/factory.py`). The default
`Config.vector_store="memory"` is a dependency-free in-memory store — great for
tests and development. For persistence set `vector_store="chroma"` and install
`memoria[vector]`; data is stored under `Config.chroma_path`.

## Docs

- [`docs/PRD.md`](docs/PRD.md) — product requirements, architecture, ADRs.
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — 路线图 · 后续规划（高铁查询 / 可视化 / 部署 / 记忆调优 / 更多 MCP / 工程增强）.
- [`AGENTS.md`](AGENTS.md) — how to work in this repo (domain model, conventions).
- [`CLAUDE.md`](CLAUDE.md) — Claude Code conventions.
- [`CHANGELOG.md`](CHANGELOG.md) — 更新日志.

## License

[MIT](LICENSE) © 2026 zzdjjdd
