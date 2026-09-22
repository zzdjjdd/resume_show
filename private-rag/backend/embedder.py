"""Qwen3-Embedding-4B 嵌入调用(走硅基流动 OpenAI 兼容接口)。"""
from __future__ import annotations

import requests
from typing import List

from .config import settings


class EmbeddingError(RuntimeError):
    pass


def _check_key() -> None:
    if not settings.SILICONFLOW_API_KEY:
        raise EmbeddingError("SILICONFLOW_API_KEY 未配置(.env)")


def embed_texts(texts: List[str]) -> List[List[float]]:
    """批量嵌入。Qwen3-Embedding 支持 batch。"""
    _check_key()
    url = f"{settings.SILICONFLOW_BASE_URL.rstrip('/')}/embeddings"
    headers = {
        "Authorization": f"Bearer {settings.SILICONFLOW_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.EMBEDDING_MODEL,
        "input": texts,
        "encoding_format": "float",
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    if resp.status_code != 200:
        raise EmbeddingError(
            f"Embedding 调用失败: HTTP {resp.status_code} -> {resp.text[:500]}"
        )
    data = resp.json()
    return [item["embedding"] for item in data["data"]]


def embed_query(text: str) -> List[float]:
    return embed_texts([text])[0]