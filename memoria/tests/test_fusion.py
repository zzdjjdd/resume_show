from memoria.retrieval.fusion import rrf


def test_rrf_single_list_order() -> None:
    scores = rrf([["a", "b", "c"]])
    assert scores["a"] > scores["b"] > scores["c"]


def test_rrf_multi_list_boost() -> None:
    scores = rrf([["a", "b"], ["a", "c"]])
    assert scores["a"] > scores["b"]
    assert scores["a"] > scores["c"]
    assert scores["b"] == scores["c"]


def test_rrf_empty() -> None:
    assert rrf([]) == {}
