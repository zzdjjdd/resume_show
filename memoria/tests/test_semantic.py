from pathlib import Path

from memoria.config import Config
from memoria.db.session import init_db, make_engine, make_sessionmaker
from memoria.embedders.fake import DeterministicFakeEmbedder
from memoria.stores.semantic import SemanticStore
from memoria.vector.memory import InMemoryVectorStore


def _make_store(tmp_path: Path) -> SemanticStore:
    cfg = Config(sqlite_url=f"sqlite:///{tmp_path / 'semantic.db'}", namespace="ns")
    engine = make_engine(cfg)
    init_db(engine)
    return SemanticStore(
        make_sessionmaker(engine),
        InMemoryVectorStore(),
        DeterministicFakeEmbedder(dim=64),
        "ns",
    )


def test_upsert_and_dedupe(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    id1 = store.upsert("user", "prefers dark theme", confidence=0.7)
    id2 = store.upsert("user", "prefers dark theme", confidence=0.9)
    assert id1 == id2
    assert store.count() == 1
    assert store.get(id1).confidence == 0.9  # merged via max


def test_upsert_source_lineage(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    rid = store.upsert("user", "prefers dark theme", source_episode_ids=["e1"])
    store.upsert("user", "prefers dark theme", source_episode_ids=["e2"])
    assert set(store.get(rid).source_episode_ids) == {"e1", "e2"}


def test_search_returns_record(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    rid = store.upsert("user", "prefers dark theme", confidence=0.9)
    hits = store.search("prefers dark theme")
    assert hits and hits[0].id == rid
    assert hits[0].layer == "semantic"
    assert hits[0].importance == 0.9


def test_delete(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    rid = store.upsert("user", "x", confidence=0.5)
    assert store.delete(rid) is True
    assert store.count() == 0
    assert store.delete(rid) is False
