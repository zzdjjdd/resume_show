from pathlib import Path

from memoria import Memory
from memoria.config import Config
from memoria.consolidation.consolidator import Consolidator
from memoria.db.session import init_db, make_engine, make_sessionmaker
from memoria.embedders.fake import DeterministicFakeEmbedder
from memoria.llms.fake import FakeLLM
from memoria.stores.episodic import EpisodicStore
from memoria.stores.semantic import SemanticStore
from memoria.stores.working import WorkingMemory
from memoria.vector.memory import InMemoryVectorStore


def _rig(tmp_path: Path, llm: FakeLLM | None = None) -> tuple:
    cfg = Config(sqlite_url=f"sqlite:///{tmp_path / 'consolidator.db'}")
    engine = make_engine(cfg)
    init_db(engine)
    sessionmaker = make_sessionmaker(engine)
    embedder = DeterministicFakeEmbedder(dim=64)
    episodic = EpisodicStore(sessionmaker, InMemoryVectorStore(), embedder, "ns")
    semantic = SemanticStore(sessionmaker, InMemoryVectorStore(), embedder, "ns")
    working = WorkingMemory()
    return Consolidator(episodic, semantic, working, llm=llm), episodic, semantic, working


# ---- heuristic path (no LLM) ----


def test_distill_facts(mem: Memory) -> None:
    mem.remember_event("我喜欢深色主题", importance=0.8)
    mem.remember_event("今天吃了午饭", importance=0.3)

    result = mem.consolidate()
    assert result["facts_distilled"] == 1

    hits = mem.recall("我喜欢深色主题", layers=["semantic"])
    assert hits and "深色主题" in hits[0].content


def test_distill_is_idempotent(mem: Memory) -> None:
    mem.remember_event("我喜欢深色主题")
    mem.consolidate()
    mem.consolidate()
    assert mem._semantic.count() == 1


def test_flush_working(mem: Memory) -> None:
    mem.working.append("user", "hi")
    mem.working.append("assistant", "hello there")

    record_id = mem.flush_working()
    assert record_id is not None
    assert len(mem.working) == 0
    row = mem._episodic.get(record_id)
    assert "对话摘要" in row.content


def test_flush_empty_working(mem: Memory) -> None:
    assert mem.flush_working() is None


# ---- LLM path (FakeLLM, offline) ----


def test_distill_with_llm(tmp_path: Path) -> None:
    llm = FakeLLM(responses=['[{"episode_id": "", "fact": "用户喜欢深色主题"}]'])
    consolidator, episodic, semantic, _working = _rig(tmp_path, llm=llm)
    episodic.add("我喜欢深色主题", importance=0.8)

    assert consolidator.distill_facts() == 1
    assert semantic.count() == 1
    assert llm.calls  # the LLM was actually consulted


def test_distill_llm_unparseable_returns_zero(tmp_path: Path) -> None:
    llm = FakeLLM(responses=["sorry, no json here"])
    consolidator, episodic, semantic, _working = _rig(tmp_path, llm=llm)
    episodic.add("我喜欢深色主题")

    assert consolidator.distill_facts() == 0
    assert semantic.count() == 0


def test_distill_only_new_episodes(tmp_path: Path) -> None:
    # Incremental: a second distill call processes only episodes added since the first.
    llm = FakeLLM(
        responses=['[{"episode_id":"","fact":"事实1"}]', '[{"episode_id":"","fact":"事实2"}]']
    )
    consolidator, episodic, semantic, _working = _rig(tmp_path, llm=llm)
    episodic.add("我喜欢A")
    consolidator.distill_facts()
    episodic.add("我喜欢B")
    assert consolidator.distill_facts() == 1
    assert semantic.count() == 2
    assert len(llm.calls) == 2  # one LLM call per batch, no reprocessing


def test_summarize_with_llm(tmp_path: Path) -> None:
    llm = FakeLLM(responses=["用户在讨论主题偏好"])
    consolidator, episodic, _semantic, working = _rig(tmp_path, llm=llm)
    working.append("user", "我喜欢深色主题")

    record_id = consolidator.summarize_working()
    assert record_id is not None
    assert "用户在讨论主题偏好" in episodic.get(record_id).content
    assert len(working) == 0


def test_summarize_falls_back_without_llm(tmp_path: Path) -> None:
    consolidator, episodic, _semantic, working = _rig(tmp_path, llm=None)
    working.append("user", "你好")

    record_id = consolidator.summarize_working()
    assert "user:你好" in episodic.get(record_id).content
