import json
from pathlib import Path

from memoria import Memory


def test_stats_counts(mem: Memory) -> None:
    mem.remember_event("an event")
    mem.upsert_fact("user", "a fact", confidence=0.9)
    mem.record_procedure("a routine", ["step"])
    stats = mem.stats()
    assert stats["counts"]["episodic"] == 1
    assert stats["counts"]["semantic"] == 1
    assert stats["counts"]["procedural"] == 1
    assert stats["embedder"] == "fake"


def test_stats_hit_rate(mem: Memory) -> None:
    stats0 = mem.stats()
    assert stats0["retrieval"]["calls"] == 0
    assert stats0["retrieval"]["hit_rate"] == 0.0

    mem.recall("nothing stored yet")  # miss (empty store)
    mem.remember_event("hello world")
    mem.recall("hello world")  # hit

    stats = mem.stats()
    assert stats["retrieval"]["calls"] == 2
    assert stats["retrieval"]["hits"] == 1
    assert stats["retrieval"]["hit_rate"] == 0.5


def test_export_dict_and_file(mem: Memory, tmp_path: Path) -> None:
    mem.remember_event("remember me")
    mem.upsert_fact("user", "prefers x", confidence=0.9)

    data = mem.export()
    assert data["namespace"] == mem.namespace
    assert len(data["layers"]["episodic"]) == 1

    path = tmp_path / "backup.json"
    mem.export(str(path))
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["layers"]["episodic"][0]["content"] == "remember me"


def test_delete_where_targets_semantic_only(mem: Memory) -> None:
    mem.remember_event("an episode")
    mem.upsert_fact("user", "银行卡尾号1234", confidence=0.9)
    mem.upsert_fact("user", "prefers dark", confidence=0.9)

    result = mem.delete_where(fact_contains="银行卡")
    assert result["semantic"] == 1
    assert result["episodic"] == 0
    assert mem._semantic.count() == 1  # only "prefers dark" remains
    assert mem._episodic.count() == 1  # episode untouched


def test_delete_where_wipes_namespace(mem: Memory) -> None:
    mem.remember_event("e1")
    mem.upsert_fact("user", "f1", confidence=0.5)
    mem.record_procedure("p1", ["s"])

    result = mem.delete_where()
    assert result["total"] == 3
    assert mem._episodic.count() == 0
    assert mem._semantic.count() == 0
    assert mem._procedural.count() == 0
