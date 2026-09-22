import uuid

from memoria.config import Config
from memoria.db.base import Base
from memoria.db.models import EpisodicMemory, SemanticMemory
from memoria.db.session import init_db, make_engine, make_sessionmaker


def test_create_and_query_with_namespace(tmp_config: Config) -> None:
    engine = make_engine(tmp_config)
    init_db(engine)
    sessionmaker = make_sessionmaker(engine)

    with sessionmaker() as session:
        session.add(
            EpisodicMemory(
                id=str(uuid.uuid4()),
                namespace=tmp_config.namespace,
                content="refactored auth module",
                importance=0.7,
            )
        )
        session.add(
            EpisodicMemory(
                id=str(uuid.uuid4()),
                namespace="other-ns",
                content="must not appear",
            )
        )
        session.commit()

        rows = (
            session.query(EpisodicMemory)
            .filter_by(namespace=tmp_config.namespace)
            .all()
        )
        assert len(rows) == 1
        assert rows[0].content == "refactored auth module"
        assert rows[0].importance == 0.7
        assert rows[0].access_count == 0
        assert rows[0].created_at is not None


def test_semantic_json_roundtrip(tmp_config: Config) -> None:
    engine = make_engine(tmp_config)
    Base.metadata.create_all(engine)
    sessionmaker = make_sessionmaker(engine)

    with sessionmaker() as session:
        session.add(
            SemanticMemory(
                id=str(uuid.uuid4()),
                namespace=tmp_config.namespace,
                subject="user",
                fact="prefers dark theme",
                confidence=0.9,
                source_episode_ids=["ep-1", "ep-2"],
            )
        )
        session.commit()

        row = session.query(SemanticMemory).first()
        assert row is not None
        assert row.subject == "user"
        assert row.source_episode_ids == ["ep-1", "ep-2"]
