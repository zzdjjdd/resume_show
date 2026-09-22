from pathlib import Path

import pytest

from memoria.config import Config
from memoria.db.session import init_db, make_engine, make_sessionmaker
from memoria.embedders.fake import DeterministicFakeEmbedder
from memoria.stores.episodic import EpisodicStore
from memoria.vector.memory import InMemoryVectorStore


def _make_store(tmp_path: Path, namespace: str) -> EpisodicStore:
    cfg = Config(sqlite_url=f"sqlite:///{tmp_path / 'episodic.db'}", namespace=namespace)
    engine = make_engine(cfg)
    init_db(engine)
    sessionmaker = make_sessionmaker(engine)
    return EpisodicStore(
        sessionmaker,
        InMemoryVectorStore(),
        DeterministicFakeEmbedder(dim=64),
        namespace,
    )


def test_add_and_count(tmp_path: Path) -> None:
    store = _make_store(tmp_path, "ns")
    record_id = store.add("refactored auth module", importance=0.8)
    assert isinstance(record_id, str)
    assert store.count() == 1


def test_search_returns_exact_match_first(tmp_path: Path) -> None:
    store = _make_store(tmp_path, "ns")
    target = store.add("the user prefers dark theme")
    store.add("an unrelated note about lunch")

    hits = store.search("the user prefers dark theme", top_k=2)
    assert hits[0].id == target
    assert hits[0].score == pytest.approx(1.0, abs=1e-6)
    assert hits[0].layer == "episodic"
    assert hits[0].content == "the user prefers dark theme"


def test_namespace_isolation(tmp_path: Path) -> None:
    cfg = Config(sqlite_url=f"sqlite:///{tmp_path / 'iso.db'}")
    engine = make_engine(cfg)
    init_db(engine)
    sessionmaker = make_sessionmaker(engine)
    embedder = DeterministicFakeEmbedder(dim=64)
    vector = InMemoryVectorStore()

    store_a = EpisodicStore(sessionmaker, vector, embedder, "user-a")
    store_b = EpisodicStore(sessionmaker, vector, embedder, "user-b")
    store_a.add("secret of a")
    store_b.add("secret of b")

    hits_a = store_a.search("secret", top_k=10)
    assert hits_a and all(h.namespace == "user-a" for h in hits_a)
    assert store_a.count() == 1
    assert store_b.count() == 1


def test_access_count_bumps(tmp_path: Path) -> None:
    store = _make_store(tmp_path, "ns")
    record_id = store.add("remember me")
    store.search("remember me")

    row = store.get(record_id)
    assert row is not None
    assert row.access_count == 1
    assert row.last_accessed_at is not None
