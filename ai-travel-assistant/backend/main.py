"""
FastAPI 入口：提供配置读写、连接测试、旅游计划生成、流式聊天接口。
静态前端由同一服务托管（路径 /static 与 /）。
"""
import json
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import ai_service, mcp_client
from .config import load_config, update_config

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = (BASE_DIR.parent / "frontend").resolve()

app = FastAPI(title="AI智行助手", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------- Schema ----------------

class ConfigSection(BaseModel):
    section: str
    payload: Dict[str, Any]


class McpTestRequest(BaseModel):
    name: str
    url: str


class ChatMessage(BaseModel):
    role: str
    content: str | None = None
    tool_calls: List[Dict[str, Any]] | None = None
    tool_call_id: str | None = None


class ChatRequest(BaseModel):
    messages: List[ChatMessage]


class TravelRequest(BaseModel):
    origin: str
    destination: str
    days: int = 1
    people: int = 2
    preferences: List[str] = []
    extra: str = ""
    use_map: bool = False


# ---------------- API ----------------

@app.get("/api/config")
def get_config():
    cfg = load_config()
    # 不回显 LLM api_key 完整值，前端可自己保留，这里直接返回
    return cfg


@app.post("/api/config")
def post_config(body: ConfigSection):
    if body.section not in ("llm", "amap", "mcp"):
        raise HTTPException(status_code=400, detail="section 必须是 llm/amap/mcp")
    cfg = update_config(body.section, body.payload)
    return {"ok": True, "config": cfg}


@app.post("/api/test/llm")
def test_llm():
    return ai_service.test_connection()


@app.post("/api/test/amap")
def test_amap():
    return ai_service.test_amap_connection()


@app.post("/api/test/mcp")
def test_mcp(body: McpTestRequest):
    """单条 MCP server 连接测试：返回 ok + 工具列表摘要。"""
    return mcp_client.test_server(body.name, body.url)


@app.post("/api/travel/plan")
def travel_plan(req: TravelRequest):
    """生成旅游计划：SSE 流式输出，每步一个 step 事件，最终一个 result 事件。"""
    payload = req.model_dump()

    def event_iter():
        for chunk in ai_service.generate_travel_plan_stream(payload):
            evt_type = chunk.get("type")
            if evt_type == "step":
                payload_out = {
                    "type": "step",
                    "phase": chunk.get("phase"),
                    "step": chunk.get("step"),
                    "title": chunk.get("title"),
                    "icon": chunk.get("icon"),
                    "content": chunk.get("content"),
                    "summary": chunk.get("summary"),
                    "data": chunk.get("data"),
                    "status": chunk.get("status"),
                }
            elif evt_type == "delta":
                payload_out = {"type": "delta", "content": chunk.get("content", "")}
            elif evt_type == "result":
                payload_out = {
                    "type": "result",
                    "ok": chunk.get("ok"),
                    "markdown": chunk.get("markdown", ""),
                    "enrichments": chunk.get("enrichments", []),
                    "message": chunk.get("message"),
                }
            elif evt_type == "error":
                payload_out = {"type": "error", "message": chunk.get("message")}
            elif evt_type == "done":
                payload_out = {"type": "done"}
            else:
                continue
            yield f"data: {json.dumps(payload_out, ensure_ascii=False)}\n\n"

    headers = {
        "Cache-Control": "no-cache",
        "Content-Type": "text/event-stream; charset=utf-8",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_iter(), headers=headers, media_type="text/event-stream")


@app.post("/api/chat")
def chat(req: ChatRequest):
    msgs = [m.model_dump(exclude_none=True) for m in req.messages]
    tool_events: List[Dict[str, Any]] = []

    def event_iter():
        for chunk in ai_service.chat_stream(msgs, tool_events=tool_events):
            evt_type = chunk.get("type")
            if evt_type == "delta":
                payload = {"type": "delta", "content": chunk.get("content", "")}
            elif evt_type == "thinking":
                payload = {"type": "thinking", "content": chunk.get("content", "")}
            elif evt_type == "tool":
                payload = {
                    "type": "tool",
                    "name": chunk.get("name"),
                    "args": chunk.get("args"),
                    "result": chunk.get("result"),
                }
            elif evt_type == "step":
                # ReAct 各阶段事件：phase=begin|delta|end, step=thought|intent|...
                payload = {
                    "type": "step",
                    "phase": chunk.get("phase"),
                    "step": chunk.get("step"),
                    "title": chunk.get("title"),
                    "icon": chunk.get("icon"),
                    "content": chunk.get("content"),
                    "summary": chunk.get("summary"),
                    "data": chunk.get("data"),
                    "decision": chunk.get("decision"),
                    "status": chunk.get("status"),
                }
            elif evt_type == "error":
                payload = {"type": "error", "message": chunk.get("message")}
            elif evt_type == "done":
                payload = {"type": "done"}
            else:
                continue
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        # 工具调用汇总供前端调试展示（如已收集）
        if tool_events:
            yield f"data: {json.dumps({'type': 'tools', 'items': tool_events}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    headers = {
        "Cache-Control": "no-cache",
        "Content-Type": "text/event-stream; charset=utf-8",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_iter(), headers=headers, media_type="text/event-stream")


# ---------------- 静态文件 ----------------

if FRONTEND_DIR.exists():
    # 静态资源
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
    index_html = FRONTEND_DIR / "index.html"

    @app.get("/")
    def root():
        if index_html.exists():
            return FileResponse(str(index_html))
        return PlainTextResponse("前端文件未找到", status_code=404)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=False)
