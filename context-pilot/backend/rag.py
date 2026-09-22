"""
RAG module - LangChain + FAISS for knowledge base retrieval
Uses SiliconFlow embedding model
"""
import os
import json
import numpy as np
from typing import List, Dict, Any, Optional
import httpx


# Default knowledge base content - sample documents
DEFAULT_DOCS = [
    {
        "id": "doc1",
        "title": "Context Pilot 产品介绍",
        "content": "Context Pilot（上下文领航员）是一款用于演示和教学 LLM 上下文管理的交互式系统。它通过可视化展示 System Prompt、对话历史、RAG 检索结果和工具调用等组件如何共同构成 LLM 的 Context Window，帮助用户理解 KV Cache、窗口溢出、Context Engineering 等关键概念。"
    },
    {
        "id": "doc2",
        "title": "Context Pilot 价格信息",
        "content": "Context Pilot 是开源教学项目，遵循 MIT 协议，可以免费下载和使用。商业部署需要联系作者获取授权。学术研究、课堂教学、个人学习场景下完全免费。"
    },
    {
        "id": "doc3",
        "title": "Context Pilot 主要功能",
        "content": "主要功能包括：1) 实时 Context 结构可视化拆解（System Prompt、对话历史、RAG、工具调用）；2) KV Cache 命中状态展示（绿色 Hit / 橙色 Recalc）；3) Token 使用趋势图；4) 窗口溢出处理策略对比（删除/摘要/智能裁剪）；5) 演示模式与实机模式切换；6) 完整的 LLM API 配置与测试。"
    },
    {
        "id": "doc4",
        "title": "上下文窗口与 KV Cache 原理",
        "content": "LLM 的上下文窗口（Context Window）指模型一次推理能处理的最大 Token 数量。KV Cache 是 Transformer 在自回归生成过程中对历史 Token 的 Key/Value 矩阵缓存，命中 Cache 可以避免重复计算，大幅提升推理速度。Cache 命中率越高，推理时延越低、成本越低。"
    },
    {
        "id": "doc5",
        "title": "高德地图 MCP 工具集",
        "content": "高德地图 MCP 提供了丰富的地图相关工具：地理编码（地址→经纬度）、逆地理编码（经纬度→地址）、IP 定位、天气查询、关键词搜索、周边搜索、详情搜索、骑行/步行/驾车/公交路径规划、距离测量等。所有工具均通过 JSON-RPC over HTTP 调用。"
    },
    {
        "id": "doc6",
        "title": "北京简介",
        "content": "北京是中华人民共和国的首都，位于华北平原北部，是中国的政治、文化、国际交往和科技创新中心。北京总面积 16410 平方公里，常住人口约 2185 万。北京著名景点包括故宫、长城、天坛、颐和园等。"
    }
]


class EmbeddingClient:
    """Client for the embedding model (SiliconFlow by default)"""

    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.model = model
        self.available = True  # Set to False after connection failure

    def embed(self, text: str) -> List[float]:
        """Get embedding for a single text"""
        if not self.available:
            raise RuntimeError("Embedding service disabled after connection failure")
        try:
            response = httpx.post(
                f"{self.base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={"input": text, "model": self.model},
                timeout=15.0
            )
            response.raise_for_status()
            data = response.json()
            return data["data"][0]["embedding"]
        except Exception as e:
            print(f"Embedding error: {e}")
            print("Embedding service disabled, falling back to keyword search.")
            self.available = False
            raise

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Get embeddings for multiple texts"""
        if not self.available:
            raise RuntimeError("Embedding service disabled after connection failure")
        try:
            response = httpx.post(
                f"{self.base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={"input": texts, "model": self.model},
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()
            return [d["embedding"] for d in data["data"]]
        except Exception as e:
            print(f"Batch embedding error: {e}")
            print("Embedding service disabled, falling back to keyword search.")
            self.available = False
            raise


class RAGStore:
    """FAISS-based RAG knowledge base with simple in-memory storage"""

    def __init__(self):
        self.docs: List[Dict[str, Any]] = []
        self.embeddings: Optional[np.ndarray] = None
        self.embedding_client: Optional[EmbeddingClient] = None
        self.index_built = False

    def configure(self, base_url: str, api_key: str, model: str):
        """Configure the embedding client"""
        self.embedding_client = EmbeddingClient(base_url, api_key, model)

    def add_documents(self, docs: List[Dict[str, Any]]):
        """Add documents to the store"""
        for doc in docs:
            # Check if already exists
            existing_ids = {d.get("id") for d in self.docs}
            if doc.get("id") not in existing_ids:
                self.docs.append(doc)
        self.index_built = False

    def load_default_kb(self):
        """Load default knowledge base"""
        self.docs = list(DEFAULT_DOCS)
        self.index_built = False

    def build_index(self):
        """Build FAISS index from documents"""
        if not self.docs:
            return False
        if not self.embedding_client or not self.embedding_client.api_key:
            # Use simple TF-IDF style fallback for demo when no API key
            self._build_fallback_index()
            return True
        try:
            texts = [d["content"] for d in self.docs]
            embeddings = self.embedding_client.embed_batch(texts)
            self.embeddings = np.array(embeddings, dtype=np.float32)
            # Normalize for cosine similarity
            norms = np.linalg.norm(self.embeddings, axis=1, keepdims=True)
            self.embeddings = self.embeddings / (norms + 1e-10)
            self.index_built = True
            return True
        except Exception as e:
            print(f"Index build error: {e}")
            self._build_fallback_index()
            return True

    def _build_fallback_index(self):
        """Fallback: use simple keyword-based scoring"""
        self.embeddings = None
        self.index_built = True
        # Pre-compute keyword frequencies
        for doc in self.docs:
            doc["_keywords"] = set(doc["content"].lower().split())
        print("RAG: Using keyword-based fallback (no embedding API key)")

    def search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Search for relevant documents"""
        if not self.index_built:
            self.build_index()
        if not self.docs:
            return []

        results = []
        if (self.embeddings is not None and self.embedding_client
                and self.embedding_client.available):
            # Vector search
            try:
                query_emb = np.array(self.embedding_client.embed(query), dtype=np.float32)
                query_emb = query_emb / (np.linalg.norm(query_emb) + 1e-10)
                scores = self.embeddings @ query_emb
                top_indices = np.argsort(scores)[::-1][:top_k]
                for idx in top_indices:
                    results.append({
                        "id": self.docs[idx].get("id"),
                        "title": self.docs[idx].get("title"),
                        "content": self.docs[idx]["content"],
                        "score": float(scores[idx])
                    })
            except Exception as e:
                print(f"Vector search failed, switching to keyword search: {e}")
                self.embeddings = None  # Permanently fall back
                results = self._keyword_search(query, top_k)
        else:
            results = self._keyword_search(query, top_k)
        return results

    def _keyword_search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Simple keyword-based search fallback"""
        query_words = set(query.lower().split())
        scored = []
        for doc in self.docs:
            content = doc["content"].lower()
            score = sum(1 for w in query_words if w in content)
            # Also check title
            title = doc.get("title", "").lower()
            score += sum(2 for w in query_words if w in title)
            if score > 0:
                scored.append((score, doc))
        scored.sort(key=lambda x: -x[0])
        results = []
        for score, doc in scored[:top_k]:
            results.append({
                "id": doc.get("id"),
                "title": doc.get("title"),
                "content": doc["content"],
                "score": float(score)
            })
        return results

    def get_all_docs(self) -> List[Dict[str, Any]]:
        return [{"id": d.get("id"), "title": d.get("title"), "preview": d["content"][:100]} for d in self.docs]


# Global RAG store
rag_store = RAGStore()
