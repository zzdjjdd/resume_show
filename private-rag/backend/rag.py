"""RAG 主流程:解析 -> 分块 -> 嵌入 -> 入库,以及 检索 -> 拼 prompt -> LLM 回答。"""
from __future__ import annotations

from pathlib import Path
from typing import List, Tuple, Optional

from .loaders import parse_file
from .splitter import split_text
from .embedder import embed_texts, embed_query
from .vectorstore import get_store
from .schemas import DocChunk, Citation
from .llm import chat, LLMError
from .config import settings


# ---------- 入库 ----------
def ingest_file(path: Path) -> Tuple[str, str, int]:
    """解析 -> 分块 -> 嵌入 -> 写入 FAISS。
    返回 (doc_id, doc_name, chunk_count)。
    """
    store = get_store()
    doc = parse_file(path)
    if store.has_doc(doc["doc_id"]):
        # 已存在,直接返回
        return doc["doc_id"], doc["doc_name"], 0

    chunks: List[DocChunk] = split_text(doc)
    if not chunks:
        return doc["doc_id"], doc["doc_name"], 0

    # 嵌入(批量)
    embeddings = embed_texts([c.text for c in chunks])
    added = store.add(chunks, embeddings, doc_name=doc["doc_name"])
    return doc["doc_id"], doc["doc_name"], added


def preview_chunks(path: Path, limit: int = 3) -> List[DocChunk]:
    """只解析 + 分块 + 返回前 N 个,不入库。"""
    doc = parse_file(path)
    chunks = split_text(doc)
    return chunks[:limit]


# ---------- 检索 ----------
def _format_context(hits: List[Tuple[DocChunk, float]]) -> str:
    blocks = []
    for i, (chunk, score) in enumerate(hits, 1):
        blocks.append(
            f"【片段{i}】 来源:{chunk.doc_name} (chunk_id={chunk.chunk_id}, 相关度={score:.3f})\n"
            f"{chunk.text}"
        )
    return "\n\n---\n\n".join(blocks)


# 简单判断:是否需要调用知识库
# - 问候/闲聊/通用知识,不需要
# - 涉及具体文档/公司/项目,需要
_GREETINGS = {"你好", "您好", "hi", "hello", "hey", "在吗", "嗨", "早上好", "下午好", "晚上好"}


def should_use_kb(question: str) -> bool:
    q = question.strip().lower()
    if not q:
        return False
    if q in _GREETINGS:
        return False
    # 命中明显的知识库关键词
    kb_keywords = [
        "点头", "教育", "研究院", "课程", "项目", "论文", "实验室",
        "自习室", "师资", "学员", "创始人", "战略", "文化", "愿景",
        "使命", "价值观", "历史", "发展", "产品", "AI", "人工智能",
        "品牌", "手册",
    ]
    return any(k in question for k in kb_keywords)


# ---------- RAG 问答 ----------
SYSTEM_PROMPT_KB = """你是湖南点头教育科技有限公司的智能助手"小点"。
你的任务是基于【参考资料】回答用户问题。要求:
1. 优先引用参考资料中的事实回答,不要编造。
2. 回答简洁、结构清晰,必要时用编号或要点列出。
3. 如果参考资料不足以回答,直接告诉用户"资料未覆盖该问题",不要臆测。
4. 回答末尾标注引用的资料来源(如:来源:《品牌手册1.docx》)。
"""

SYSTEM_PROMPT_GENERAL = """你是湖南点头教育科技有限公司的智能助手"小点"。
回答要简洁、得体、有礼貌。如果用户没明确问公司业务,可正常聊天。"""


def answer(question: str, history: list = None, top_k: int = None) -> dict:
    """返回 {"answer", "reasoning", "used_kb", "citations"}。"""
    history = history or []
    top_k = top_k or settings.TOP_K

    use_kb = should_use_kb(question)
    citations: List[Citation] = []
    context_block: str = ""

    if use_kb:
        store = get_store()
        if store.index is not None and store.index.ntotal > 0:
            q_vec = embed_query(question)
            hits = store.search(q_vec, top_k=top_k)
            for chunk, score in hits:
                citations.append(
                    Citation(
                        doc_name=chunk.doc_name,
                        chunk_id=chunk.chunk_id,
                        text=chunk.text,
                        score=score,
                    )
                )
            if hits:
                context_block = _format_context(hits)

    # 拼 messages
    sys_prompt = SYSTEM_PROMPT_KB if (use_kb and context_block) else SYSTEM_PROMPT_GENERAL
    if use_kb and context_block:
        sys_prompt += f"\n\n【参考资料】\n{context_block}\n"

    messages = [{"role": "system", "content": sys_prompt}]
    # history 最多取最近 6 轮,避免 token 爆炸
    for m in history[-12:]:
        messages.append({"role": m.get("role", "user"), "content": m.get("content", "")})
    messages.append({"role": "user", "content": question})

    try:
        result = chat(messages)
    except LLMError as e:
        return {
            "answer": f"[模型调用失败] {e}",
            "reasoning": None,
            "used_kb": use_kb,
            "citations": citations,
        }

    return {
        "answer": result["content"],
        "reasoning": result.get("reasoning"),
        "used_kb": bool(use_kb and context_block),
        "citations": citations,
    }