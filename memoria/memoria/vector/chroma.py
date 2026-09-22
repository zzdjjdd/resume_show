"""Chroma-backed persistent vector store (lazy import).

Construction is offline; the persistent client and collection are only opened
on first use. Uses cosine distance so ``score = 1 - distance``.
"""

from __future__ import annotations

from typing import Any

from ..errors import VectorStoreError
from .base import VectorHit, VectorStore

# Chroma metadata values must be str/int/float/bool (not None).
_ALLOWED_META = (str, int, float, bool)


def _sanitize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in metadata.items() if isinstance(v, _ALLOWED_META)}


def _to_chroma_where(where: dict[str, Any] | None) -> dict[str, Any] | None:
    if not where:
        return None
    clauses = [{key: {"$eq": value}} for key, value in where.items()]
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


class ChromaVectorStore(VectorStore):
    def __init__(self, path: str = ".chroma", collection: str = "memoria", **_: Any) -> None:
        self._path = path
        self._collection_name = collection
        self._collection: Any = None

    def _col(self) -> Any:
        if self._collection is None:
            try:
                import chromadb
            except ImportError as exc:  # pragma: no cover - depends on env
                raise VectorStoreError(
                    "chromadb is not installed. Run: pip install 'memoria[vector]'"
                ) from exc
            client = chromadb.PersistentClient(path=self._path)
            self._collection = client.get_or_create_collection(
                self._collection_name, metadata={"hnsw:space": "cosine"}
            )
        return self._collection

    def upsert(self, id: str, vector: list[float], metadata: dict[str, Any] | None = None) -> None:
        self._col().upsert(
            ids=[id],
            embeddings=[list(vector)],
            metadatas=[_sanitize_metadata(metadata or {})],
        )

    def query(
        self,
        vector: list[float],
        top_k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[VectorHit]:
        result = self._col().query(
            query_embeddings=[list(vector)],
            n_results=max(1, top_k),
            where=_to_chroma_where(where),
        )
        ids: list[str] = result["ids"][0]
        distances = result.get("distances") or [[]]
        metadatas = result.get("metadatas") or [[]]
        dist_row = distances[0]
        meta_row = metadatas[0]
        hits: list[VectorHit] = []
        for index, id in enumerate(ids):
            distance = dist_row[index] if index < len(dist_row) else None
            score = (1.0 - distance) if distance is not None else 0.0
            metadata = meta_row[index] if index < len(meta_row) else {}
            hits.append(VectorHit(id=id, score=score, metadata=metadata or {}))
        return hits

    def delete(self, ids: list[str]) -> None:
        if ids:
            self._col().delete(ids=list(ids))

    def count(self) -> int:
        return int(self._col().count())
