"""FastAPI 应用入口。"""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import List

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import rag
from .config import settings, ROOT
from .schemas import (
    ParseResponse,
    DocChunk,
    IngestResponse,
    KnowledgeStats,
    ChatRequest,
    ChatResponse,
)
from .vectorstore import get_store


app = FastAPI(title="点头 RAG 本地知识库", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- 静态前端 ----------
FRONTEND_DIR = ROOT / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
def index():
    html_path = FRONTEND_DIR / "index.html"
    if html_path.exists():
        return FileResponse(str(html_path))
    return JSONResponse({"message": "前端未找到,请检查 frontend/index.html"})


# ---------- 健康检查 ----------
@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "embedding_model": settings.EMBEDDING_MODEL,
        "llm_model": settings.LLM_MODEL,
    }


# ---------- 解析预览(不入库) ----------
@app.post("/api/parse/preview", response_model=ParseResponse)
def parse_preview(file: UploadFile = File(...)):
    """解析上传的文件,返回分块预览(不入库)。"""
    if not file.filename:
        raise HTTPException(400, "未提供文件名")

    tmp_path = settings.UPLOAD_DIR / f"preview_{uuid.uuid4().hex[:8]}_{file.filename}"
    with open(tmp_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        chunks: List[DocChunk] = rag.preview_chunks(tmp_path, limit=5)
        doc_id = chunks[0].doc_id if chunks else "preview"
    except Exception as e:
        raise HTTPException(400, f"解析失败: {e}")
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass

    return ParseResponse(
        doc_id=doc_id,
        doc_name=file.filename,
        chunk_count=len(chunks),  # 仅预览数量
        preview=chunks,
    )


# ---------- 入库 ----------
@app.post("/api/ingest/upload", response_model=IngestResponse)
def ingest_upload(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(400, "未提供文件名")
    # 先存到 data/uploads
    save_path = settings.UPLOAD_DIR / file.filename
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        doc_id, doc_name, n = rag.ingest_file(save_path)
    except Exception as e:
        raise HTTPException(500, f"入库失败: {e}")

    store = get_store()
    return IngestResponse(
        doc_id=doc_id,
        doc_name=doc_name,
        chunk_count=n,
        total_chunks=len(store.chunks),
        message="已加入知识库" if n > 0 else "文档已在知识库中(去重)",
    )


# 把本地 data 下的某个文件入库(用于初始化品牌手册)
@app.post("/api/ingest/local")
def ingest_local(path: str):
    p = Path(path)
    if not p.exists():
        raise HTTPException(404, f"文件不存在: {path}")
    try:
        doc_id, doc_name, n = rag.ingest_file(p)
    except Exception as e:
        raise HTTPException(500, f"入库失败: {e}")
    return {"doc_id": doc_id, "doc_name": doc_name, "chunk_count": n}


# ---------- 知识库统计 ----------
@app.get("/api/kb/stats", response_model=KnowledgeStats)
def kb_stats():
    store = get_store()
    s = store.stats()
    return KnowledgeStats(**s)


# ---------- 列出某文档的所有分块 ----------
@app.get("/api/kb/doc/{doc_id}/chunks", response_model=List[DocChunk])
def list_doc_chunks(doc_id: str):
    store = get_store()
    chunks = store.list_chunks_by_doc(doc_id)
    return chunks


# ---------- 删除某文档 ----------
@app.delete("/api/kb/doc/{doc_id}")
def del_doc(doc_id: str):
    store = get_store()
    ok = store.remove_doc(doc_id)
    return {"removed": ok, "doc_id": doc_id}


# ---------- 问答 ----------
@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    history = [m.model_dump() for m in req.history]
    result = rag.answer(
        req.question,
        history=history,
        top_k=req.top_k,
    )
    return ChatResponse(
        answer=result["answer"],
        reasoning=result.get("reasoning"),
        used_kb=result["used_kb"],
        citations=result.get("citations", []),
    )


# ---------- 启动事件:首次启动自动入库种子文档 ----------
SEED_EXTENSIONS = (".pdf", ".docx", ".txt", ".md")


def _seed_files() -> List[Path]:
    """种子文档:`data/seed/` 下所有支持格式,外加根目录遗留的品牌手册。"""
    files: List[Path] = []
    seed_dir = settings.DATA_DIR / "seed"
    if seed_dir.exists():
        files += sorted(p for p in seed_dir.iterdir() if p.suffix.lower() in SEED_EXTENSIONS)
    legacy = ROOT / "品牌手册1.docx"
    if legacy.exists():
        files.append(legacy)
    return files


@app.on_event("startup")
def auto_ingest_seed_docs():
    store = get_store()
    from .loaders import _doc_id_for

    for path in _seed_files():
        doc_id = _doc_id_for(path)
        if doc_id in store.docs:
            print(f"[启动] 已在库中,跳过: {path.name}")
            continue
        try:
            doc_id, doc_name, n = rag.ingest_file(path)
            print(f"[启动] 入库完成: {doc_name} (doc_id={doc_id}, chunks={n})")
        except Exception as e:
            print(f"[启动] 入库失败: {path.name} -> {e}")