"""FAISS 向量库管理:构建、追加、检索、持久化。"""
from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import List, Dict, Tuple, Any

import numpy as np
import faiss

from .config import settings
from .schemas import DocChunk


class FaissStore:
    """封装一个 FAISS IndexFlatIP(内积)+ 元数据(JSON)。

    索引和元数据分开存储,便于增删。
    注:FAISS C++ 端在 Windows 上 fopen 时不认子目录+中文路径组合,
       因此索引文件统一存到 INDEX_DIR/_idx/ 纯 ASCII 子目录;
       但 FAISS 把 '_idx/faiss.index' 当成单一文件名写入,所以这里
       使用 INDEX_DIR(可能中文)直接做父目录 + ASCII 文件名。
    """

    def __init__(self, index_dir: Path = None):
        self.index_dir: Path = index_dir or settings.INDEX_DIR
        self.index_dir.mkdir(parents=True, exist_ok=True)
        # 把 faiss 索引文件放到一个固定英文名(不带子目录)
        self.index_path = self.index_dir / "_faiss.index"
        self.meta_path = self.index_dir / "metadata.pkl"
        self.docs_summary_path = self.index_dir / "docs.json"

        self.index: faiss.IndexFlatIP | None = None
        self.chunks: List[DocChunk] = []  # 与 index 行号一一对应
        self.docs: Dict[str, Dict[str, Any]] = {}  # doc_id -> {doc_name, chunk_count}
        self._load()

    # ---------- 持久化 ----------
    def _load(self) -> None:
        if self.index_path.exists() and self.meta_path.exists():
            try:
                self.index = faiss.read_index(str(self.index_path))
                with open(self.meta_path, "rb") as f:
                    self.chunks = pickle.load(f)
                if self.docs_summary_path.exists():
                    with open(self.docs_summary_path, "r", encoding="utf-8") as f:
                        self.docs = json.load(f)
            except Exception as e:
                print(f"[FaissStore] 加载已有索引失败,重建: {e}")
                self.index = None
                self.chunks = []
                self.docs = {}

    def _save(self) -> None:
        if self.index is None:
            return
        # 索引文件直接写到 _idx 子目录(纯 ASCII 路径,FAISS 可写)
        faiss.write_index(self.index, str(self.index_path))
        with open(self.meta_path, "wb") as f:
            pickle.dump(self.chunks, f)
        with open(self.docs_summary_path, "w", encoding="utf-8") as f:
            json.dump(self.docs, f, ensure_ascii=False, indent=2)

    # ---------- 写入 ----------
    def add(
        self,
        chunks: List[DocChunk],
        embeddings: List[List[float]],
        doc_name: str,
    ) -> int:
        if not chunks:
            return 0
        assert len(chunks) == len(embeddings), "chunks 与 embeddings 数量不一致"

        vectors = np.asarray(embeddings, dtype="float32")
        # 归一化,便于用内积 ≈ 余弦
        faiss.normalize_L2(vectors)

        if self.index is None:
            self.index = faiss.IndexFlatIP(vectors.shape[1])
            self._save_dim = vectors.shape[1]
        else:
            assert vectors.shape[1] == self.index.d, (
                f"向量维度不一致: 现有 {self.index.d} vs 新增 {vectors.shape[1]}"
            )

        self.index.add(vectors)
        self.chunks.extend(chunks)
        doc_id = chunks[0].doc_id
        self.docs[doc_id] = {
            "doc_name": doc_name,
            "chunk_count": len(chunks),
        }
        self._save()
        return len(chunks)

    def remove_doc(self, doc_id: str) -> bool:
        """按 doc_id 重建索引(简单可靠,避免逐行删除复杂度)。"""
        keep_idx = [i for i, c in enumerate(self.chunks) if c.doc_id != doc_id]
        if len(keep_idx) == len(self.chunks):
            return False
        if not keep_idx:
            self.index = None
            self.chunks = []
            self.docs.pop(doc_id, None)
            self._save()
            return True

        # 重建
        old_index = self.index
        old_chunks = self.chunks
        new_chunks = [old_chunks[i] for i in keep_idx]
        # 通过 add + remove 不行,这里直接重建
        # 把所有现有向量重新组装
        # FAISS 不支持直接按 index 取向量,所以重建
        # 取巧:重新跑一次 embedding 没必要 — 我们用 IndexFlatIP,可以从 index 里 reconstruct
        vectors = np.zeros((len(keep_idx), old_index.d), dtype="float32")
        for new_i, old_i in enumerate(keep_idx):
            vectors[new_i] = old_index.reconstruct(old_i)

        new_index = faiss.IndexFlatIP(old_index.d)
        faiss.normalize_L2(vectors)
        new_index.add(vectors)

        self.index = new_index
        self.chunks = new_chunks
        self.docs.pop(doc_id, None)
        self._save()
        return True

    def has_doc(self, doc_id: str) -> bool:
        return doc_id in self.docs

    # ---------- 检索 ----------
    def search(self, query_vec: List[float], top_k: int = 4) -> List[Tuple[DocChunk, float]]:
        if self.index is None or self.index.ntotal == 0:
            return []
        q = np.asarray([query_vec], dtype="float32")
        faiss.normalize_L2(q)
        scores, idxs = self.index.search(q, min(top_k, self.index.ntotal))
        results: List[Tuple[DocChunk, float]] = []
        for score, idx in zip(scores[0], idxs[0]):
            if idx < 0 or idx >= len(self.chunks):
                continue
            results.append((self.chunks[int(idx)], float(score)))
        return results

    # ---------- 状态 ----------
    def stats(self) -> Dict[str, Any]:
        return {
            "doc_count": len(self.docs),
            "chunk_count": len(self.chunks),
            "docs": [
                {"doc_id": did, **info}
                for did, info in self.docs.items()
            ],
        }

    def list_chunks_by_doc(self, doc_id: str) -> List[DocChunk]:
        return [c for c in self.chunks if c.doc_id == doc_id]


# 全局单例(简单实现,够用)
_store: FaissStore | None = None


def get_store() -> FaissStore:
    global _store
    if _store is None:
        _store = FaissStore()
    return _store