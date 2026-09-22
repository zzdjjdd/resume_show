from memoria.config import Config


def test_defaults() -> None:
    cfg = Config()
    assert cfg.embedder == "fake"
    assert cfg.namespace == "default"
    assert cfg.sqlite_url.endswith("memoria.db")
    assert cfg.extra == {}


def test_overrides() -> None:
    cfg = Config(namespace="user:42", embedder="local", embedder_dim=768)
    assert cfg.namespace == "user:42"
    assert cfg.embedder == "local"
    assert cfg.embedder_dim == 768
