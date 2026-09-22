import math

import pytest

from memoria.embedders.factory import available_embedders, get_embedder
from memoria.embedders.fake import DeterministicFakeEmbedder
from memoria.errors import ConfigError


def test_fake_is_deterministic(fake_embedder: DeterministicFakeEmbedder) -> None:
    a = fake_embedder.embed("hello world")
    b = fake_embedder.embed("hello world")
    assert a == b
    assert len(a) == fake_embedder.dim


def test_fake_differs_by_text(fake_embedder: DeterministicFakeEmbedder) -> None:
    assert fake_embedder.embed("cat") != fake_embedder.embed("dog")


def test_fake_is_normalized(fake_embedder: DeterministicFakeEmbedder) -> None:
    vec = fake_embedder.embed("some text")
    norm = math.sqrt(sum(x * x for x in vec))
    assert math.isclose(norm, 1.0, rel_tol=1e-6)


def test_factory_returns_fake() -> None:
    emb = get_embedder("fake", dim=32)
    assert isinstance(emb, DeterministicFakeEmbedder)
    assert emb.dim == 32


def test_factory_unknown_raises() -> None:
    with pytest.raises(ConfigError):
        get_embedder("does-not-exist")


def test_available_embedders() -> None:
    assert "fake" in available_embedders()
    assert "local" in available_embedders()
    assert "openai" in available_embedders()


def test_local_constructs_offline() -> None:
    # Construction must not require sentence-transformers to be installed;
    # the model is only loaded on first embed() call.
    emb = get_embedder("local", model="all-MiniLM-L6-v2", dim=384)
    assert emb.dim == 384


def test_openai_compatible_with_dimensions() -> None:
    # Qwen text-embedding-v3 style: OpenAI-compatible + flexible dimensions.
    from memoria.embedders.openai import OpenAIEmbedder

    emb = get_embedder(
        "openai", model="text-embedding-v3", base_url="http://example.local", dimensions=1024
    )
    assert isinstance(emb, OpenAIEmbedder)
    assert emb.dim == 1024
