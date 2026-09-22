import pytest

from memoria import Memory
from memoria.errors import ConfigError


def test_recall_spans_layers(mem: Memory) -> None:
    mem.remember_event("user prefers dark theme", importance=0.8)
    mem.upsert_fact("user", "prefers dark theme", confidence=0.9)
    mem.record_procedure("deploy to production", ["run tests"])

    hits = mem.recall("dark theme preference")
    layers = {h.layer for h in hits}
    assert "episodic" in layers
    assert "semantic" in layers
    # scores are sorted descending after RRF + strength re-rank
    assert all(hits[i].score >= hits[i + 1].score for i in range(len(hits) - 1))


def test_recall_layer_filter(mem: Memory) -> None:
    mem.remember_event("an episodic note")
    hits = mem.recall("an episodic note", layers=["episodic"])
    assert hits and all(h.layer == "episodic" for h in hits)


def test_recall_unknown_layer(mem: Memory) -> None:
    with pytest.raises(ConfigError):
        mem.recall("q", layers=["nope"])


def test_build_context(mem: Memory) -> None:
    mem.working.append("user", "I like dark mode")
    mem.upsert_fact("user", "likes dark mode", confidence=0.9)
    ctx = mem.build_context(query="dark mode")
    assert "[工作记忆]" in ctx
    assert "I like dark mode" in ctx
    assert "[长期记忆]" in ctx


def test_build_context_working_only(mem: Memory) -> None:
    mem.working.append("user", "hello")
    ctx = mem.build_context()
    assert "hello" in ctx
    assert "[长期记忆]" not in ctx
