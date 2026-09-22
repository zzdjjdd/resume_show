from pathlib import Path

import pytest

from memoria.errors import ConfigError
from memoria.vector.factory import available_vector_stores, get_vector_store
from memoria.vector.memory import InMemoryVectorStore, cosine_similarity


def test_cosine_similarity() -> None:
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_query_ordering() -> None:
    vs = InMemoryVectorStore()
    vs.upsert("a", [1.0, 0.0])
    vs.upsert("b", [0.0, 1.0])
    vs.upsert("c", [0.9, 0.1])
    hits = vs.query([1.0, 0.0], top_k=3)
    assert [h.id for h in hits] == ["a", "c", "b"]


def test_top_k_limit() -> None:
    vs = InMemoryVectorStore()
    for i in range(5):
        vs.upsert(f"id{i}", [float(i), 1.0])
    assert len(vs.query([1.0, 1.0], top_k=2)) == 2


def test_where_filter() -> None:
    vs = InMemoryVectorStore()
    vs.upsert("a", [1.0, 0.0], {"namespace": "ns1"})
    vs.upsert("b", [1.0, 0.0], {"namespace": "ns2"})
    hits = vs.query([1.0, 0.0], top_k=5, where={"namespace": "ns1"})
    assert [h.id for h in hits] == ["a"]


def test_delete_and_count() -> None:
    vs = InMemoryVectorStore()
    vs.upsert("a", [1.0])
    vs.upsert("b", [1.0])
    assert vs.count() == 2
    vs.delete(["a", "missing"])
    assert vs.count() == 1


def test_factory_unknown_raises() -> None:
    with pytest.raises(ConfigError):
        get_vector_store("nope")


def test_available_vector_stores() -> None:
    assert {"memory", "chroma"} <= set(available_vector_stores())


def test_chroma_constructs_offline(tmp_path: Path) -> None:
    # Construction must not import chromadb; the client opens on first use.
    vs = get_vector_store("chroma", path=str(tmp_path), collection="t")
    assert vs is not None
