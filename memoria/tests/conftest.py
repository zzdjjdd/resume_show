"""Shared fixtures.

Tests run fully offline: embedding uses the deterministic fake embedder, the
vector store is in-memory, and databases are throwaway SQLite files under
pytest's tmp_path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from memoria import Memory
from memoria.config import Config
from memoria.embedders.fake import DeterministicFakeEmbedder


@pytest.fixture
def fake_embedder() -> DeterministicFakeEmbedder:
    return DeterministicFakeEmbedder(dim=64)


@pytest.fixture
def tmp_config(tmp_path: Path) -> Config:
    return Config(
        sqlite_url=f"sqlite:///{tmp_path / 'memoria_test.db'}",
        namespace="test-ns",
        embedder="fake",
        embedder_dim=64,
    )


@pytest.fixture
def mem(tmp_config: Config) -> Memory:
    memory = Memory(tmp_config)
    memory.init_db()
    return memory
