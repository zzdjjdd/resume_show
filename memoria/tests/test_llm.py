import pytest

from memoria.errors import ConfigError
from memoria.llms.factory import available_llms, get_llm
from memoria.llms.fake import FakeLLM
from memoria.llms.openai_compat import OpenAICompatLLM


def test_fake_llm_responses_and_calls() -> None:
    llm = FakeLLM(responses=["first", "second"])
    assert llm.complete("a") == "first"
    assert llm.complete("b") == "second"
    assert llm.complete("c") == ""  # exhausted
    assert llm.calls == ["a", "b", "c"]


def test_factory_returns_types() -> None:
    assert isinstance(get_llm("fake"), FakeLLM)
    assert isinstance(get_llm("deepseek"), OpenAICompatLLM)
    assert isinstance(get_llm("openai-compat"), OpenAICompatLLM)


def test_factory_unknown_raises() -> None:
    with pytest.raises(ConfigError):
        get_llm("does-not-exist")


def test_available_llms() -> None:
    assert {"fake", "deepseek", "openai"} <= set(available_llms())


def test_openai_compat_constructs_offline() -> None:
    # Construction must not import openai or require credentials.
    llm = OpenAICompatLLM(model="deepseek-v4-flash", base_url="http://example.local")
    assert llm is not None


def test_fake_llm_chat() -> None:
    llm = FakeLLM(responses=["hi"])
    out = llm.chat([{"role": "user", "content": "你好"}], system="sys")
    assert out == "hi"
    assert llm.last_system == "sys"
    assert llm.calls == ["你好"]


def test_openai_compat_has_chat() -> None:
    llm = OpenAICompatLLM(model="deepseek-chat")
    assert callable(llm.chat)
