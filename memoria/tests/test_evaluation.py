from memoria import Memory
from memoria.evaluation import evaluate_recall


def test_evaluate_recall_all_hit(mem: Memory) -> None:
    mem.remember_event("alpha one")
    mem.remember_event("beta two")
    mem.remember_event("gamma three")

    cases = [
        ("alpha one", "alpha one"),
        ("beta two", "beta two"),
        ("gamma three", "gamma three"),
    ]
    report = evaluate_recall(mem, cases, top_k=3)
    assert report["total"] == 3
    assert report["hit_rate"] == 1.0
    assert report["misses"] == []


def test_evaluate_recall_miss(mem: Memory) -> None:
    mem.remember_event("only this memory")
    report = evaluate_recall(
        mem, [("a completely different query", "NOT_PRESENT_ANYWHERE")], top_k=3
    )
    assert report["hits"] == 0
    assert report["hit_rate"] == 0.0
    assert len(report["misses"]) == 1
    assert report["misses"][0]["expected"] == "NOT_PRESENT_ANYWHERE"
