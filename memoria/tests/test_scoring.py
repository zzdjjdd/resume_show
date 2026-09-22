from datetime import UTC, datetime, timedelta

from memoria.retrieval.scoring import TAU, recency_decay, strength


def test_recency_decay() -> None:
    assert recency_decay(0.0, 100.0) == 1.0
    assert recency_decay(100.0, 100.0) < 0.5  # exp(-1) ≈ 0.37
    assert recency_decay(50.0, 0.0) == 1.0  # tau<=0 -> no decay


def test_strength_recent_beats_old() -> None:
    now = datetime(2026, 8, 2, tzinfo=UTC)
    recent = now - timedelta(days=1)
    old = now - timedelta(days=200)
    assert strength(0.8, recent, 0, TAU["episodic"], now) > strength(
        0.8, old, 0, TAU["episodic"], now
    )


def test_strength_access_boost() -> None:
    now = datetime(2026, 8, 2, tzinfo=UTC)
    created = now - timedelta(days=1)
    assert strength(0.5, created, 10, TAU["episodic"], now) > strength(
        0.5, created, 0, TAU["episodic"], now
    )


def test_strength_handles_naive_datetime() -> None:
    now = datetime(2026, 8, 2, tzinfo=UTC)
    naive = datetime(2026, 8, 1)  # what SQLite returns
    assert strength(0.5, naive, 0, TAU["episodic"], now) > 0


def test_strength_none_created() -> None:
    assert strength(0.5, None, 0, TAU["semantic"]) > 0
