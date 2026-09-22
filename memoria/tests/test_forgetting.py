import uuid
from datetime import timedelta

from memoria import Memory
from memoria.db.base import utcnow
from memoria.db.models import EpisodicMemory


def test_forget_weak_episodic(mem: Memory) -> None:
    # insert an ancient, unimportant episode directly (no vector entry needed)
    old = utcnow() - timedelta(days=400)
    with mem.session() as session:
        session.add(
            EpisodicMemory(
                id=str(uuid.uuid4()),
                namespace=mem.namespace,
                content="ancient trivia",
                importance=0.05,
                created_at=old,
            )
        )
        session.commit()
    strong_id = mem.remember_event("important and recent", importance=0.9)

    removed = mem.forget(threshold=0.05)
    assert removed == 1
    assert mem._episodic.get(strong_id) is not None


def test_forget_respects_max_keep(mem: Memory) -> None:
    for i in range(5):
        mem.remember_event(f"episode {i}", importance=0.9)
    removed = mem.forget(threshold=0.0, max_keep=2)
    assert removed == 3
    assert mem._episodic.count() == 2
