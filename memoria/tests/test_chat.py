from memoria import Memory
from memoria.config import Config
from memoria.llms.fake import FakeLLM


def _mem(tmp_config: Config, llm: FakeLLM | None = None) -> Memory:
    mem = Memory(tmp_config, llm=llm)
    mem.init_db()
    return mem


def test_chat_with_fake_llm(tmp_config: Config) -> None:
    llm = FakeLLM(responses=["你好！我记得你。", "[]"])
    mem = _mem(tmp_config, llm=llm)
    res = mem.chat("你好")
    assert res["reply"] == "你好！我记得你。"
    assert len(mem.working) == 2  # user + assistant
    assert mem._episodic.count() == 1  # exchange stored


def test_chat_without_llm(tmp_config: Config) -> None:
    mem = _mem(tmp_config)
    res = mem.chat("你好")
    assert "LLM" in res["reply"]
    assert len(mem.working) == 2


def test_chat_injects_recalled_memory(tmp_config: Config) -> None:
    llm = FakeLLM(responses=["ok"])
    mem = _mem(tmp_config, llm=llm)
    mem.upsert_fact("user", "prefers blue", confidence=0.9)
    mem.chat("what color do I like", consolidate=False)
    assert llm.last_system is not None
    assert "prefers blue" in llm.last_system


def test_chat_distills_facts(tmp_config: Config) -> None:
    responses = ["reply-1", '[{"episode_id":"","fact":"用户喜欢蓝色"}]']
    llm = FakeLLM(responses=responses)
    mem = _mem(tmp_config, llm=llm)
    res = mem.chat("我喜欢蓝色")
    assert res["reply"] == "reply-1"
    assert res["distilled_facts"] == 1
    assert mem._semantic.count() == 1


def test_chat_no_distill_without_llm(tmp_config: Config) -> None:
    mem = _mem(tmp_config)
    res = mem.chat("hello")
    assert res["distilled_facts"] == 0
