"""
Context Pilot - Main FastAPI Application
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from context_manager import ContextManager, DEMO_STEPS, count_tokens
from rag import rag_store
from mcp_client import mcp_client, detect_tool_need, get_tool_definitions, AMAP_TOOLS
from llm_client import llm_client

app = FastAPI(title="Context Pilot", version="1.0.0")

# Static files
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "..", "frontend")
STATIC_DIR = os.path.join(FRONTEND_DIR, "static")
TEMPLATES_DIR = os.path.join(FRONTEND_DIR, "templates")

# CORS - allow all origins for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Global state
context_mgr = ContextManager(max_tokens=2048)
context_mgr.set_system_prompt(
    "你是 Context Pilot，一个用于演示 LLM 上下文管理的智能助手。"
    "你的回答应该简洁清晰，必要时使用工具获取实时信息。"
)
rag_store.load_default_kb()

# Global settings storage
SETTINGS_FILE = os.path.join(BASE_DIR, "..", "data", "settings.json")


def load_settings() -> Dict[str, Any]:
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_settings(settings: Dict[str, Any]):
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def apply_settings(settings: Dict[str, Any]):
    """Apply settings to all clients"""
    # LLM
    llm = settings.get("llm", {})
    if llm.get("base_url") and llm.get("api_key"):
        llm_client.configure(
            llm.get("base_url", ""),
            llm.get("api_key", ""),
            llm.get("model", "MiniMax-M3"),
            llm.get("temperature", 0.7)
        )
    # MCP
    mcp = settings.get("mcp", {})
    if mcp.get("url") and mcp.get("api_key"):
        mcp_client.configure(mcp.get("url", ""), mcp.get("api_key", ""))
    # Embedding
    emb = settings.get("embedding", {})
    if emb.get("base_url") and emb.get("api_key"):
        rag_store.configure(
            emb.get("base_url", ""),
            emb.get("api_key", ""),
            emb.get("model", "Qwen/Qwen3-Embedding-4B")
        )
    # Context window
    cw = settings.get("context_window", 2048)
    if isinstance(cw, int) and cw > 0:
        context_mgr.max_tokens = cw


# Load settings on startup
apply_settings(load_settings())


# ============== Request/Response Models ==============
class ChatRequest(BaseModel):
    message: str
    mode: str = "chat"  # "chat" or "demo"


class SettingsRequest(BaseModel):
    settings: Dict[str, Any]


class StrategyRequest(BaseModel):
    strategy: str  # "delete", "summary", "trim"


class TestConnectionRequest(BaseModel):
    type: str  # "llm", "embedding", "mcp"


class RAGAddRequest(BaseModel):
    documents: List[Dict[str, Any]]


# ============== Routes ==============

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the main UI"""
    return templates.TemplateResponse(request, "index.html")


@app.get("/api/context")
async def get_context():
    """Get current context structure"""
    return context_mgr.get_context_structure()


@app.get("/api/messages")
async def get_messages():
    """Get all chat messages"""
    return {
        "messages": context_mgr.messages,
        "demo_active": False
    }


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """Send a chat message"""
    user_msg = req.message.strip()
    if not user_msg:
        raise HTTPException(400, "消息不能为空")

    # Add user message to context (this also determines cache hit)
    user_msg_obj = context_mgr.add_message("user", user_msg)
    was_cache_hit = user_msg_obj.get("cache_hit", False)

    # Decide: RAG? Tool? Both?
    tool_call = None
    rag_used = False
    tool_used = False

    if req.mode == "chat":
        # Check for tool call need
        tool_call = detect_tool_need(user_msg)
        if tool_call and mcp_client.enabled:
            try:
                result = mcp_client.call_tool(tool_call["tool"], tool_call["args"])
                context_mgr.add_tool_call(
                    tool_call["tool"],
                    tool_call["args"],
                    json.dumps(result.get("result", {}), ensure_ascii=False)[:500]
                )
                tool_used = True
            except Exception as e:
                print(f"Tool call error: {e}")

        # Check for RAG need (simple keyword: 知识库, 文档, 产品, etc.)
        rag_keywords = ["产品", "多少钱", "功能", "介绍", "什么是", "知识库", "文档", "如何", "怎么用"]
        if any(kw in user_msg for kw in rag_keywords):
            results = rag_store.search(user_msg, top_k=2)
            if results:
                context_mgr.add_rag_result(user_msg, results)
                rag_used = True

    # Build prompt for LLM
    messages_for_llm = [{"role": "system", "content": context_mgr.system_prompt}]

    # Add RAG context if used
    if context_mgr.rag_results:
        last_rag = context_mgr.rag_results[-1]
        messages_for_llm.append({
            "role": "system",
            "content": f"参考知识库信息：\n{last_rag['content']}"
        })

    # Add recent history (limit to fit window)
    for m in context_mgr.messages[-10:]:
        messages_for_llm.append({
            "role": m["role"],
            "content": m["content"]
        })

    # Add tool call context if used
    if tool_used and context_mgr.tool_calls:
        last_tool = context_mgr.tool_calls[-1]
        messages_for_llm.append({
            "role": "system",
            "content": f"工具调用结果：{last_tool['result']}"
        })

    # Get response
    response_text = llm_client.chat(messages_for_llm)

    # Add assistant message
    context_mgr.add_assistant_message(response_text, cache_hit=was_cache_hit)

    # Check overflow
    usage = context_mgr.get_usage_percent()
    overflow = usage >= 100

    return {
        "user_message": user_msg,
        "user_cache_hit": was_cache_hit,
        "response": response_text,
        "rag_used": rag_used,
        "tool_used": tool_used,
        "tool_call": tool_call,
        "context": context_mgr.get_context_structure(),
        "overflow": overflow
    }


@app.post("/api/strategy")
async def apply_strategy(req: StrategyRequest):
    """Apply a context window overflow strategy"""
    if req.strategy == "delete":
        result = context_mgr.strategy_delete()
    elif req.strategy == "summary":
        result = context_mgr.strategy_summary()
    elif req.strategy == "trim":
        result = context_mgr.strategy_trim()
    else:
        raise HTTPException(400, f"未知策略: {req.strategy}")
    return {
        "result": result,
        "context": context_mgr.get_context_structure()
    }


@app.post("/api/reset")
async def reset_context():
    """Reset the context"""
    context_mgr.reset()
    return {
        "success": True,
        "context": context_mgr.get_context_structure()
    }


@app.get("/api/demo/steps")
async def get_demo_steps():
    """Get all demo steps"""
    return DEMO_STEPS


@app.post("/api/demo/execute")
async def execute_demo_step(data: dict):
    """Execute a demo step"""
    stage = data.get("stage")
    step_idx = data.get("step", 0)

    if stage not in DEMO_STEPS:
        raise HTTPException(400, f"未知阶段: {stage}")
    stage_data = DEMO_STEPS[stage]
    if step_idx >= len(stage_data["steps"]):
        raise HTTPException(400, "步骤索引超出范围")

    step = stage_data["steps"][step_idx]
    user_input = step.get("user_input", "")
    expected = step.get("expected_response", "")

    # Reset context at the start of each stage for clean demo
    if step_idx == 0:
        context_mgr.reset()

    # Add user message
    user_msg_obj = context_mgr.add_message("user", user_input)
    cache_hit = user_msg_obj.get("cache_hit", False)

    # Handle tool calls in demo - use mock mode (no real MCP needed)
    if "tool_call" in step:
        tc = step["tool_call"]
        # Demo mode uses mock tool calls regardless of settings
        result = mcp_client.call_tool(tc["tool"], tc["args"])
        context_mgr.add_tool_call(
            tc["tool"],
            tc["args"],
            json.dumps(result.get("result", {}), ensure_ascii=False)[:500]
        )

    # Handle RAG in demo
    if stage == "stage3_rag_tool" and step_idx == 0:
        results = rag_store.search(user_input, top_k=2)
        if results:
            context_mgr.add_rag_result(user_input, results)

    # Add assistant response
    context_mgr.add_assistant_message(expected, cache_hit=cache_hit)

    return {
        "step": step,
        "user_message": user_input,
        "user_cache_hit": cache_hit,
        "response": expected,
        "context": context_mgr.get_context_structure(),
        "has_next": step_idx + 1 < len(stage_data["steps"])
    }


@app.get("/api/settings")
async def get_settings():
    """Get current settings"""
    settings = load_settings()
    # Return masked api_key (only show whether it's set + masked preview)
    def mask_key(k):
        if not k:
            return ""
        if len(k) <= 8:
            return "*" * len(k)
        return k[:4] + "*" * (len(k) - 8) + k[-4:]

    return {
        "llm": {
            "base_url": settings.get("llm", {}).get("base_url", "https://api.minimaxi.com/v1"),
            "model": settings.get("llm", {}).get("model", "MiniMax-M3"),
            "temperature": settings.get("llm", {}).get("temperature", 0.7),
            "api_key_set": bool(settings.get("llm", {}).get("api_key")),
            "api_key_masked": mask_key(settings.get("llm", {}).get("api_key", ""))
        },
        "mcp": {
            "url": settings.get("mcp", {}).get("url", ""),
            "api_key_set": bool(settings.get("mcp", {}).get("api_key")),
            "api_key_masked": mask_key(settings.get("mcp", {}).get("api_key", ""))
        },
        "embedding": {
            "base_url": settings.get("embedding", {}).get("base_url", "https://api.siliconflow.cn/v1"),
            "model": settings.get("embedding", {}).get("model", "Qwen/Qwen3-Embedding-4B"),
            "api_key_set": bool(settings.get("embedding", {}).get("api_key")),
            "api_key_masked": mask_key(settings.get("embedding", {}).get("api_key", ""))
        },
        "context_window": settings.get("context_window", 2048)
    }


@app.post("/api/settings")
async def update_settings(req: SettingsRequest):
    """Update settings"""
    current = load_settings()
    new_settings = req.settings

    # Preserve existing API keys if not being changed
    for section in ["llm", "mcp", "embedding"]:
        if section in new_settings:
            if section not in current:
                current[section] = {}
            for k, v in new_settings[section].items():
                if k == "api_key" and (not v or v == ""):
                    # Don't overwrite if not provided
                    continue
                current[section][k] = v
    # Context window
    if "context_window" in new_settings:
        current["context_window"] = int(new_settings["context_window"])

    save_settings(current)
    apply_settings(current)
    return {"success": True, "message": "设置已保存"}


@app.post("/api/test-connection")
async def test_connection(req: TestConnectionRequest):
    """Test connection to LLM / Embedding / MCP"""
    settings = load_settings()
    if req.type == "llm":
        llm = settings.get("llm", {})
        if not llm.get("api_key"):
            return {"success": False, "message": "未配置 API Key，请先在设置中填写"}
        if not llm.get("base_url"):
            return {"success": False, "message": "未配置 Base URL"}
        llm_client.configure(
            llm.get("base_url"),
            llm.get("api_key"),
            llm.get("model", "MiniMax-M3")
        )
        return llm_client.test_connection()
    elif req.type == "embedding":
        emb = settings.get("embedding", {})
        if not emb.get("api_key"):
            return {"success": False, "message": "未配置 API Key，请先在设置中填写"}
        if not emb.get("base_url"):
            return {"success": False, "message": "未配置 Base URL"}
        rag_store.configure(
            emb.get("base_url"),
            emb.get("api_key"),
            emb.get("model", "Qwen/Qwen3-Embedding-4B")
        )
        try:
            test_emb = rag_store.embedding_client.embed("test") if rag_store.embedding_client else None
            if test_emb:
                return {"success": True, "message": f"Embedding连接成功，向量维度: {len(test_emb)}"}
            return {"success": False, "message": "Embedding客户端未配置"}
        except Exception as e:
            return {"success": False, "message": f"Embedding连接失败: {str(e)}"}
    elif req.type == "mcp":
        mcp = settings.get("mcp", {})
        # Always allow mock mode (no key required)
        mcp_client.configure(mcp.get("url", ""), mcp.get("api_key", ""))
        if mcp_client.mock_mode:
            return {
                "success": True,
                "message": "MCP模拟模式已启用（未配置真实URL/Key）。工具调用将返回内置模拟数据。配置URL和Key后可切换到真实模式。"
            }
        return mcp_client.test_connection()
    return {"success": False, "message": f"未知类型: {req.type}"}


@app.get("/api/rag/documents")
async def get_rag_documents():
    """Get all RAG documents"""
    return {"documents": rag_store.get_all_docs()}


@app.post("/api/rag/add")
async def add_rag_documents(req: RAGAddRequest):
    """Add documents to RAG"""
    rag_store.add_documents(req.documents)
    rag_store.build_index()
    return {"success": True, "count": len(rag_store.docs)}


@app.post("/api/rag/search")
async def search_rag(data: dict):
    """Search RAG"""
    query = data.get("query", "")
    top_k = data.get("top_k", 3)
    results = rag_store.search(query, top_k=top_k)
    return {"results": results}


@app.get("/api/mcp/tools")
async def get_mcp_tools():
    """Get all available MCP tools"""
    return {
        "tools": AMAP_TOOLS,
        "enabled": mcp_client.enabled
    }


@app.post("/api/mcp/call")
async def call_mcp(data: dict):
    """Call an MCP tool"""
    tool = data.get("tool")
    args = data.get("args", {})
    result = mcp_client.call_tool(tool, args)
    if result.get("success"):
        context_mgr.add_tool_call(
            tool, args,
            json.dumps(result.get("result", {}), ensure_ascii=False)[:500]
        )
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
