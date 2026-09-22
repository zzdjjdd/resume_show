"""主程序：FastAPI 应用入口"""
import json
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from .config_store import load_config, save_config
from .llm_client import LLMClient
from .amap_mcp import AmapMCPClient, summarize_amap_result
from .mcp_client import MCPClient
from .travel_planner import generate_travel_plan
from .chat_agent import ChatAgent


# ---------- 数据模型 ----------
class LLMConfigIn(BaseModel):
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    timeout: int = 60


class AmapConfigIn(BaseModel):
    api_key: str = ""
    sse_url: str = "https://mcp.amap.com/v1/sse"


class MCPConfigIn(BaseModel):
    server_url: str = ""
    enabled: bool = False
    timeout: int = 30


class UIConfigIn(BaseModel):
    theme: str = "auto"


class FullConfig(BaseModel):
    llm: LLMConfigIn = Field(default_factory=LLMConfigIn)
    amap: AmapConfigIn = Field(default_factory=AmapConfigIn)
    mcp: MCPConfigIn = Field(default_factory=MCPConfigIn)
    mcp2: MCPConfigIn = Field(default_factory=MCPConfigIn)
    ui: UIConfigIn = Field(default_factory=UIConfigIn)


class TestConnIn(BaseModel):
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    timeout: Optional[int] = None


class TravelIn(BaseModel):
    departure: str
    destination: str
    days: int = 1
    people: int = 1
    preferences: List[str] = []
    additional: str = ""


class ChatIn(BaseModel):
    message: str
    history: List[Dict[str, str]] = []


# ---------- 应用初始化 ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动期:根据配置尝试初始化 MCP 客户端。失败时仅记录日志,不影响主流程。"""
    cfg = load_config()
    mcp_cfg = cfg.get("mcp", {}) or {}
    app.state.mcp_client = None
    app.state.mcp_error = None
    if mcp_cfg.get("enabled") and mcp_cfg.get("server_url"):
        client = MCPClient(
            server_url=mcp_cfg["server_url"],
            timeout=int(mcp_cfg.get("timeout", 30) or 30),
        )
        ok = await client.initialize()
        if ok:
            app.state.mcp_client = client
            print(f"[mcp] 已加载 {len(client.list_tools())} 个工具 from {mcp_cfg['server_url'][:60]}")
        else:
            app.state.mcp_error = client.init_error
            print(f"[mcp] 初始化失败: {client.init_error}")
    yield


app = FastAPI(title="AI智行助手", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
PLANS_DIR = Path(__file__).resolve().parent.parent / "plans"


def _mcp_from_state() -> Optional[MCPClient]:
    """从 app.state 取已初始化的 MCP client(若没有则返回 None)。"""
    return getattr(app.state, "mcp_client", None)


def _cfg_dict_to_model(cfg: Dict[str, Any]) -> FullConfig:
    return FullConfig(**cfg)


def _amap_from_cfg(cfg: Dict[str, Any], api_key_override: Optional[str] = None) -> AmapMCPClient:
    amap_cfg = cfg.get("amap", {}) or {}
    api_key = api_key_override if api_key_override else amap_cfg.get("api_key", "")
    return AmapMCPClient(
        api_key=api_key,
        sse_url=amap_cfg.get("sse_url", "https://mcp.amap.com/v1/sse"),
        server_url=cfg.get("mcp", {}).get("server_url", ""),
    )


def _llm_from_cfg(cfg: Dict[str, Any], llm_override: Optional[Dict[str, Any]] = None) -> LLMClient:
    llm_cfg = dict(cfg.get("llm", {}) or {})
    if llm_override:
        llm_cfg.update({k: v for k, v in llm_override.items() if v})
    return LLMClient(
        api_key=llm_cfg.get("api_key", ""),
        base_url=llm_cfg.get("base_url", "https://api.openai.com/v1"),
        model=llm_cfg.get("model", "gpt-4o-mini"),
        timeout=int(llm_cfg.get("timeout", 60) or 60),
    )


# ---------- 配置接口 ----------
@app.get("/api/config")
async def get_config():
    return load_config()


@app.post("/api/config")
async def update_config(cfg: FullConfig):
    save_config(cfg.model_dump())
    return {"ok": True}


@app.post("/api/config/llm")
async def update_llm(llm: LLMConfigIn):
    cfg = load_config()
    cfg["llm"] = llm.model_dump()
    save_config(cfg)
    return {"ok": True}


@app.post("/api/config/amap")
async def update_amap(amap: AmapConfigIn):
    cfg = load_config()
    cfg["amap"] = amap.model_dump()
    save_config(cfg)
    return {"ok": True}


@app.post("/api/config/mcp")
async def update_mcp(mcp: MCPConfigIn):
    cfg = load_config()
    cfg["mcp"] = mcp.model_dump()
    save_config(cfg)
    return {"ok": True}


@app.post("/api/config/mcp2")
async def update_mcp2(mcp: MCPConfigIn):
    """保存第二个外部 MCP 服务(服务 2)的配置。

    目前仅落盘 + 供连接测试;接入聊天 Agent 的工具聚合为后续工作。
    """
    cfg = load_config()
    cfg["mcp2"] = mcp.model_dump()
    save_config(cfg)
    return {"ok": True}


# ---------- 连接测试 ----------
@app.post("/api/test/llm")
async def test_llm(in_: TestConnIn):
    cfg = load_config()
    override = in_.model_dump(exclude_none=True)
    llm = _llm_from_cfg(cfg, override)
    result = await llm.test_connection()
    return result


@app.post("/api/test/amap")
async def test_amap(payload: Dict[str, Any] = Body(default={})):
    cfg = load_config()
    api_key_override = payload.get("api_key")
    amap = _amap_from_cfg(cfg, api_key_override=api_key_override)
    if not amap.api_key:
        return {"ok": False, "error": "高德 API Key 为空"}
    # 试一下地理编码：以北京市政府为例
    res = await amap.call_tool("maps_geo", {"address": "北京市人民政府"})
    return {"ok": res.get("success", False), "result": res}


# ---------- MCP ----------
class MCPCallIn(BaseModel):
    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


@app.get("/api/mcp/tools")
async def mcp_list_tools():
    """返回已加载的 MCP 工具列表(OpenAI function-call 格式)。"""
    client = _mcp_from_state()
    if not client:
        err = getattr(app.state, "mcp_error", None) or "MCP 未启用或未初始化"
        return {"ok": False, "error": err, "tools": []}
    return {"ok": True, "tools": client.list_tools(), "server_info": client.server_info}


@app.post("/api/mcp/refresh")
async def mcp_refresh():
    """强制重新 initialize + list_tools。"""
    cfg = load_config()
    mcp_cfg = cfg.get("mcp", {}) or {}
    if not mcp_cfg.get("enabled"):
        return {"ok": False, "error": "MCP 未启用,请先在设置中勾选启用"}
    if not mcp_cfg.get("server_url"):
        return {"ok": False, "error": "server_url 为空"}
    client = MCPClient(
        server_url=mcp_cfg["server_url"],
        timeout=int(mcp_cfg.get("timeout", 30) or 30),
    )
    ok = await client.initialize()
    if not ok:
        app.state.mcp_client = None
        app.state.mcp_error = client.init_error
        return {"ok": False, "error": client.init_error, "tools": []}
    app.state.mcp_client = client
    app.state.mcp_error = None
    return {"ok": True, "tools": client.list_tools(), "server_info": client.server_info}


@app.post("/api/mcp/call")
async def mcp_call(payload: MCPCallIn):
    """手动调用一个 MCP 工具(供前端测试用)。"""
    client = _mcp_from_state()
    if not client:
        return {"ok": False, "error": "MCP 未启用"}
    res = await client.call_tool(payload.name, payload.arguments)
    return {"ok": res.get("success", False), "result": res}


@app.post("/api/test/mcp")
async def test_mcp(payload: Dict[str, Any] = Body(default={})):
    """测试 MCP 连接(临时 override server_url / timeout)。"""
    server_url = payload.get("server_url") or load_config().get("mcp", {}).get("server_url", "")
    if not server_url:
        return {"ok": False, "error": "MCP server_url 为空"}
    timeout = int(payload.get("timeout") or load_config().get("mcp", {}).get("timeout", 30) or 30)
    client = MCPClient(server_url=server_url, timeout=timeout)
    ok = await client.initialize()
    if not ok:
        return {"ok": False, "error": client.init_error, "tools": []}
    return {
        "ok": True,
        "tools_count": len(client.list_tools()),
        "tools_preview": [t.get("function", {}).get("name", "") for t in client.list_tools()][:10],
        "server_info": client.server_info,
    }


@app.post("/api/llm/models")
async def list_models(in_: TestConnIn):
    cfg = load_config()
    override = in_.model_dump(exclude_none=True)
    llm = _llm_from_cfg(cfg, override)
    if not llm.api_key:
        return {"models": [], "error": "API Key 为空"}
    models = await llm.list_models()
    return {"models": models}


# ---------- 旅游计划 ----------
@app.post("/api/travel/plan")
async def travel_plan(payload: TravelIn):
    cfg = load_config()
    if not cfg.get("llm", {}).get("api_key"):
        return JSONResponse(status_code=400, content={"ok": False, "error": "请先在设置中填写 LLM API Key"})
    llm = _llm_from_cfg(cfg)
    res = await generate_travel_plan(llm, payload.model_dump())
    if not res.get("success"):
        return JSONResponse(status_code=500, content={"ok": False, "error": res.get("error", "生成失败")})
    plan_id = f"plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    PLANS_DIR.mkdir(parents=True, exist_ok=True)
    plan_file = PLANS_DIR / f"{plan_id}.md"
    header = f"# 旅游计划 {plan_id}\n\n> 出发地：**{payload.departure}** / 目的地：**{payload.destination}** / 天数：**{payload.days}** / 人数：**{payload.people}**\n\n"
    plan_file.write_text(header + res["markdown"], encoding="utf-8")
    return {"ok": True, "plan_id": plan_id, "markdown": res["markdown"]}


@app.get("/api/travel/plans")
async def list_plans():
    PLANS_DIR.mkdir(parents=True, exist_ok=True)
    items = []
    for p in sorted(PLANS_DIR.glob("*.md"), reverse=True):
        stat = p.stat()
        items.append({
            "plan_id": p.stem,
            "name": p.stem,
            "size": stat.st_size,
            "modified": stat.st_mtime,
        })
    return {"plans": items}


@app.get("/api/travel/plan/{plan_id}")
async def get_plan(plan_id: str):
    p = PLANS_DIR / f"{plan_id}.md"
    if not p.exists():
        raise HTTPException(404, "未找到该计划")
    text = p.read_text(encoding="utf-8")
    return {"plan_id": plan_id, "markdown": text}


# ---------- 聊天 ----------
@app.post("/api/chat")
async def chat(payload: ChatIn):
    cfg = load_config()
    if not cfg.get("llm", {}).get("api_key"):
        return JSONResponse(status_code=400, content={"ok": False, "error": "请先在设置中填写 LLM API Key"})
    llm = _llm_from_cfg(cfg)
    amap = _amap_from_cfg(cfg)
    mcp = _mcp_from_state()
    agent = ChatAgent(llm, amap, mcp)
    res = await agent.chat(payload.history, payload.message)
    return res


@app.post("/api/chat/stream")
async def chat_stream(payload: ChatIn):
    cfg = load_config()
    if not cfg.get("llm", {}).get("api_key"):
        return JSONResponse(status_code=400, content={"ok": False, "error": "请先在设置中填写 LLM API Key"})
    llm = _llm_from_cfg(cfg)
    amap = _amap_from_cfg(cfg)
    mcp = _mcp_from_state()
    agent = ChatAgent(llm, amap, mcp)

    async def gen():
        async for ev in agent.stream_chat(payload.history, payload.message):
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


# ---------- 静态前端 ----------
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    async def index():
        return FileResponse(str(FRONTEND_DIR / "index.html"))

    @app.get("/config")
    async def page_config():
        return FileResponse(str(FRONTEND_DIR / "config.html"))

    @app.get("/chat")
    async def page_chat():
        return FileResponse(str(FRONTEND_DIR / "chat.html"))

    @app.get("/plan")
    async def page_plan():
        return FileResponse(str(FRONTEND_DIR / "plan.html"))

    @app.get("/plan-detail")
    async def page_plan_detail():
        return FileResponse(str(FRONTEND_DIR / "plan-detail.html"))


# ---------- 健康检查 ----------
@app.get("/api/health")
async def health():
    return {"ok": True, "time": time.time()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app:app", host="0.0.0.0", port=8765, reload=False)
