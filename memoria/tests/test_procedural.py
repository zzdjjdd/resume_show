from pathlib import Path

from memoria.config import Config
from memoria.db.session import init_db, make_engine, make_sessionmaker
from memoria.embedders.fake import DeterministicFakeEmbedder
from memoria.stores.procedural import ProceduralStore
from memoria.vector.memory import InMemoryVectorStore


def _make_store(tmp_path: Path) -> ProceduralStore:
    cfg = Config(sqlite_url=f"sqlite:///{tmp_path / 'procedural.db'}", namespace="ns")
    engine = make_engine(cfg)
    init_db(engine)
    return ProceduralStore(
        make_sessionmaker(engine),
        InMemoryVectorStore(),
        DeterministicFakeEmbedder(dim=64),
        "ns",
    )


def test_add_and_search(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    rid = store.add("deploy to production", ["run tests", "build", "canary release"])
    hits = store.search("deploy to production")
    assert hits and hits[0].id == rid
    assert hits[0].layer == "procedural"
    assert hits[0].metadata["steps"] == ["run tests", "build", "canary release"]


def test_reinforce(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    rid = store.add("deploy", ["test"])
    store.reinforce(rid, True)
    store.reinforce(rid, True)
    store.reinforce(rid, False)
    row = store.get(rid)
    assert row.success_count == 2
    assert row.failure_count == 1


def test_importance_grows_with_success(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    rid = store.add("deploy", ["test"])
    base = store.search("deploy")[0].importance
    store.reinforce(rid, True)
    boosted = store.search("deploy")[0].importance
    assert boosted > base
