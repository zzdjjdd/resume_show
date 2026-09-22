"""文本分块。优先按段落切分,过长段落再按字符滑窗,产出稳定的 chunk_id。"""
from __future__ import annotations

import re
from typing import List, Dict, Any

from .schemas import DocChunk
from .config import settings


# 中文/英文段落分隔
PARA_SPLIT = re.compile(r"\n\s*\n")


def _split_long(text: str, size: int, overlap: int) -> List[str]:
    """对超长单段做滑窗切分。"""
    if len(text) <= size:
        return [text]
    step = max(1, size - overlap)
    return [text[i : i + size] for i in range(0, len(text), step)]


def split_text(doc: Dict[str, Any], chunk_size: int = None, overlap: int = None) -> List[DocChunk]:
    """对单文档做分块,生成 DocChunk 列表。"""
    chunk_size = chunk_size or settings.CHUNK_SIZE
    overlap = overlap or settings.CHUNK_OVERLAP
    text: str = doc["text"]

    paragraphs = [p.strip() for p in PARA_SPLIT.split(text) if p.strip()]
    # 对每个段落做长度限制
    pieces: List[str] = []
    for p in paragraphs:
        if len(p) <= chunk_size:
            pieces.append(p)
        else:
            pieces.extend(_split_long(p, chunk_size, overlap))

    # 对过短的碎段(标题/单字符)做合并:把连续短段拼到 chunk_size
    merged: List[str] = []
    buf = ""
    for piece in pieces:
        if not buf:
            buf = piece
        elif len(buf) + len(piece) + 1 <= chunk_size:
            buf = buf + "\n" + piece
        else:
            merged.append(buf.strip())
            buf = piece
    if buf.strip():
        merged.append(buf.strip())

    doc_id = doc["doc_id"]
    doc_name = doc["doc_name"]
    chunks: List[DocChunk] = []
    for i, t in enumerate(merged):
        chunks.append(
            DocChunk(
                chunk_id=f"{doc_id}_{i:04d}",
                doc_id=doc_id,
                doc_name=doc_name,
                text=t,
                metadata={"chunk_index": i, "char_len": len(t)},
            )
        )
    return chunks