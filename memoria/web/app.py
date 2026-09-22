"""FastAPI server exposing Memoria to the web UI.

Run:
    pip install -e ".[web]"
    python -m uvicorn web.app:app --reload
    open http://127.0.0.1:8000

Configuration (env vars, all optional):
    MEMORIA_SQLITE_URL      default sqlite:///:memory:  (file path to persist rows)
    MEMORIA_VECTOR_STORE    default "memory"  (set "chroma" + memoria[vector] to persist vectors)
    MEMORIA_CHROMA_PATH     default web/.chroma
    MEMORIA_EMBEDDER        default "fake"  ("local"/"openai" for real semantics)
    MEMORIA_EMBEDDER_MODEL  e.g. text-embedding-v3 (Qwen) or text-embedding-3-small (OpenAI)
    MEMORIA_EMBEDDER_DIMENSIONS  output size for flexible-dim models (e.g. 1024)
    EMBEDDER_API_KEY / EMBEDDER_BASE_URL   credentials for the embedder endpoint
    MEMORIA_LLM             "deepseek" / "openai" / "openai-compat" (default: none)
    MEMORIA_LLM_MODEL       e.g. deepseek-v4-flash
    MEMORIA_LLM_BASE_URL    OpenAI-compatible LLM endpoint
    LLM_API_KEY / DEEPSEEK_API_KEY   credentials for the LLM endpoint
    MEMORIA_NAMESPACE       default "web-demo"

Note: the default keeps structured + vector stores both in-process so a demo
restarts cleanly. For durable memory, point MEMORIA_SQLITE_URL at a file AND set
MEMORIA_VECTOR_STORE=chroma so both survive restarts together.
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from memoria import Config, Memory
from memoria.agent import Agent

WEB_DIR = Path(__file__).parent

try:  # optional: pick up a local .env so `uvicorn web.app:app` works out of the box
    from dotenv import load_dotenv

    load_dotenv(WEB_DIR.parent / ".env")
except ImportError:  # python-dotenv is only needed for .env convenience
    pass


def _int_env(name: str) -> int | None:
    value = os.environ.get(name)
    return int(value) if value else None


def _make_memory() -> Memory:
    config = Config(
        sqlite_url=os.environ.get("MEMORIA_SQLITE_URL", "sqlite:///:memory:"),
        vector_store=os.environ.get("MEMORIA_VECTOR_STORE", "memory"),
        chroma_path=os.environ.get("MEMORIA_CHROMA_PATH", str(WEB_DIR / ".chroma")),
        embedder=os.environ.get("MEMORIA_EMBEDDER", "fake"),
        embedder_model=os.environ.get("MEMORIA_EMBEDDER_MODEL"),
        embedder_dimensions=_int_env("MEMORIA_EMBEDDER_DIMENSIONS"),
        llm=os.environ.get("MEMORIA_LLM"),
        llm_model=os.environ.get("MEMORIA_LLM_MODEL"),
        llm_base_url=os.environ.get("MEMORIA_LLM_BASE_URL"),
        working_max_messages=_int_env("MEMORIA_WORKING_MAX_MESSAGES"),
        namespace=os.environ.get("MEMORIA_NAMESPACE", "web-demo"),
    )
    memory = Memory(config)
    memory.init_db()
    return memory


mem = _make_memory()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Connect to the AMap MCP server (if configured) and build the agent."""
    mcp_server = None
    amap_key = os.environ.get("AMAP_MAPS_API_KEY")
    amap_url = os.environ.get("MEMORIA_AMAP_MCP_URL")
    if not amap_url and amap_key:
        amap_url = f"https://mcp.amap.com/sse?key={amap_key}"
    if amap_url:
        try:
            from memoria.mcp.remote import RemoteMCPToolServer

            server = RemoteMCPToolServer(amap_url)
            await server.connect()
            mcp_server = server
            connected_tools = await server.list_tools()
            print(
                f"[memoria] AMap MCP connected · {len(connected_tools)} tools",
                file=sys.stderr,
            )
        except Exception as exc:  # keep the app up even if MCP is unavailable
            print(f"[memoria] AMap MCP unavailable: {exc}", file=sys.stderr)
            mcp_server = None
    app.state.mcp = mcp_server
    app.state.agent = Agent(mem, mcp=mcp_server)
    yield
    if mcp_server is not None:
        await mcp_server.close()


app = FastAPI(title="Memoria API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class RememberIn(BaseModel):
    content: str
    importance: float = 0.5


class RecallIn(BaseModel):
    query: str
    top_k: int = 5


class ProcedureIn(BaseModel):
    trigger: str
    steps: list[str]


class DeleteIn(BaseModel):
    subject: str | None = None
    fact_contains: str | None = None
    content_contains: str | None = None
    trigger_contains: str | None = None


class ChatIn(BaseModel):
    message: str


@app.get("/api/health")
def health(request: Request) -> dict[str, Any]:
    return {
        "ok": True,
        "namespace": mem.namespace,
        "embedder": mem.config.embedder,
        "llm": mem.config.llm or "none",
        "mcp": getattr(request.app.state, "mcp", None) is not None,
    }


@app.get("/api/dump")
def dump() -> dict[str, Any]:
    """Full snapshot of every layer (for rendering the console bins)."""
    return mem.snapshot()


@app.post("/api/remember")
def remember(body: RememberIn) -> dict[str, Any]:
    mem.working.append("user", body.content)
    episodic_id = mem.remember_event(body.content, importance=body.importance)
    distilled = mem.consolidate()["facts_distilled"]
    return {"episodic_id": episodic_id, "distilled_facts": distilled}


@app.post("/api/recall")
def recall(body: RecallIn) -> list[dict[str, Any]]:
    hits = mem.recall(body.query, top_k=body.top_k)
    return [
        {
            "id": h.id,
            "layer": h.layer,
            "content": h.content,
            "score": round(h.score, 4),
            "importance": h.importance,
        }
        for h in hits
    ]


@app.post("/api/procedure")
def add_procedure(body: ProcedureIn) -> dict[str, str]:
    return {"id": mem.record_procedure(body.trigger, body.steps)}


@app.post("/api/chat")
async def chat(body: ChatIn, request: Request) -> dict[str, Any]:
    """Chat with the memory-augmented, tool-using agent."""
    agent: Agent = request.app.state.agent
    return await agent.run(body.message)


@app.get("/api/tools")
async def tools(request: Request) -> dict[str, Any]:
    """List the tools exposed by connected MCP servers."""
    mcp_server = getattr(request.app.state, "mcp", None)
    if mcp_server is None:
        return {"connected": False, "tools": []}
    tool_list = await mcp_server.list_tools()
    return {
        "connected": True,
        "tools": [
            {"name": getattr(t, "name", ""), "description": getattr(t, "description", "") or ""}
            for t in tool_list
        ],
    }


@app.post("/api/flush")
def flush() -> dict[str, Any]:
    return {"episodic_id": mem.flush_working()}


@app.post("/api/forget")
def forget() -> dict[str, int]:
    return {"removed": mem.forget(threshold=0.05)}


@app.get("/api/stats")
def stats() -> dict[str, Any]:
    """Observability: per-layer counts + retrieval hit-rate."""
    return mem.stats()


@app.get("/api/export")
def export() -> dict[str, Any]:
    """Export the whole namespace as JSON."""
    return mem.export()


@app.post("/api/delete")
def delete(body: DeleteIn) -> dict[str, int]:
    """Right to be forgotten: delete matching memories (no body = wipe namespace)."""
    return mem.delete_where(
        subject=body.subject,
        fact_contains=body.fact_contains,
        content_contains=body.content_contains,
        trigger_contains=body.trigger_contains,
    )


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")
