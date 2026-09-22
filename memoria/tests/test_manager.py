from memoria import Memory
from memoria.config import Config
from memoria.embedders.fake import DeterministicFakeEmbedder


def test_construct(tmp_config: Config) -> None:
    mem = Memory(tmp_config)
    assert mem.namespace == "test-ns"
    assert isinstance(mem.embedder, DeterministicFakeEmbedder)
    assert mem.vector_store is not None


def test_embedder_injection(tmp_config: Config) -> None:
    custom = DeterministicFakeEmbedder(dim=16)
    mem = Memory(tmp_config, embedder=custom)
    assert mem.embedder is custom


def test_working_memory_attached(tmp_config: Config) -> None:
    mem = Memory(tmp_config)
    mem.working.append("user", "hi")
    assert len(mem.working) == 1


def test_remember_and_recall(mem: Memory) -> None:
    record_id = mem.remember_event("refactored auth module", importance=0.8)
    hits = mem.recall("refactored auth module")
    assert any(h.id == record_id and h.layer == "episodic" for h in hits)


def test_upsert_fact_and_recall(mem: Memory) -> None:
    record_id = mem.upsert_fact("user", "prefers dark theme", confidence=0.9)
    hits = mem.recall("theme preference", layers=["semantic"])
    assert any(h.id == record_id for h in hits)


def test_record_procedure_and_recall(mem: Memory) -> None:
    record_id = mem.record_procedure("deploy to production", ["run tests", "build"])
    hits = mem.recall("deploy to production", layers=["procedural"])
    assert any(h.id == record_id for h in hits)


def test_reinforce_procedure(mem: Memory) -> None:
    record_id = mem.record_procedure("deploy", ["test"])
    assert mem.reinforce_procedure(record_id, success=True) is True


def test_consolidate_and_flush(mem: Memory) -> None:
    mem.working.append("user", "我喜欢深色主题")
    mem.flush_working()  # working -> episodic summary
    result = mem.consolidate()  # episodic -> semantic
    assert result["facts_distilled"] >= 1


def test_forget_runs(mem: Memory) -> None:
    mem.remember_event("something", importance=0.9)
    assert mem.forget(threshold=0.0) == 0  # nothing weak enough
