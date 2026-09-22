"""Pydantic 数据模型(API 入参/出参)。"""
from __future__ import annotations

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


# ---------- 文档解析 ----------
class DocChunk(BaseModel):
    chunk_id: str
    doc_id: str
    doc_name: str
    text: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ParseResponse(BaseModel):
    doc_id: str
    doc_name: str
    chunk_count: int
    preview: List[DocChunk] = Field(default_factory=list)  # 前若干块预览


# ---------- 上传 + 入库 ----------
class IngestResponse(BaseModel):
    doc_id: str
    doc_name: str
    chunk_count: int
    total_chunks: int
    message: str = "ok"


class KnowledgeStats(BaseModel):
    doc_count: int
    chunk_count: int
    docs: List[Dict[str, Any]] = Field(default_factory=list)


# ---------- 对话 ----------
class ChatMessage(BaseModel):
    role: str  # "user" | "assistant" | "system"
    content: str


class Citation(BaseModel):
    doc_name: str
    chunk_id: str
    text: str
    score: float


class ChatRequest(BaseModel):
    question: str
    history: List[ChatMessage] = Field(default_factory=list)
    top_k: Optional[int] = None
    use_kb: Optional[bool] = None  # None=自动判断


class ChatResponse(BaseModel):
    answer: str
    reasoning: Optional[str] = None  # MiniMax-M3 思考内容
    used_kb: bool
    citations: List[Citation] = Field(default_factory=list)
    session_id: Optional[str] = None