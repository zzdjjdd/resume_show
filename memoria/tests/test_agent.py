import asyncio

from memoria import Memory
from memoria.agent import Agent
from memoria.config import Config
from memoria.llms.fake import FakeLLM
from memoria.mcp.fake import FakeMCPToolServer, FakeTool


def _mem(tmp_config: Config, llm: FakeLLM | None) -> Memory:
    mem = Memory(tmp_config, llm=llm)
    mem.init_db()
    return mem


def test_agent_tool_loop(tmp_config: Config) -> None:
    tool_calls = [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "maps_weather", "arguments": '{"city":"北京"}'},
        }
    ]
    llm = FakeLLM(
        chat_tool_script=[
            (None, tool_calls),  # round 1: request a tool call
            ("北京今天晴，20℃。", None),  # round 2: final answer
        ]
    )
    tools = [FakeTool("maps_weather", "天气查询")]
    mcp = FakeMCPToolServer(tools=tools, results={"maps_weather": "晴，20℃"})
    agent = Agent(_mem(tmp_config, llm), mcp=mcp)

    res = asyncio.run(agent.run("北京天气怎么样", consolidate=False))
    assert "晴" in res["reply"]
    assert res["tools_called"] == ["maps_weather"]
    assert mcp.calls == [("maps_weather", {"city": "北京"})]


def test_agent_without_tools(tmp_config: Config) -> None:
    llm = FakeLLM(responses=["你好！"])
    agent = Agent(_mem(tmp_config, llm))  # no MCP
    res = asyncio.run(agent.run("hi", consolidate=False))
    assert res["reply"] == "你好！"
    assert res["tools_called"] == []


def test_agent_without_llm(tmp_config: Config) -> None:
    agent = Agent(_mem(tmp_config, None))
    res = asyncio.run(agent.run("hi"))
    assert "LLM" in res["reply"]


def test_agent_stores_exchange(tmp_config: Config) -> None:
    llm = FakeLLM(responses=["ok", "[]"])  # reply, then distill returns no facts
    mem = _mem(tmp_config, llm)
    agent = Agent(mem)
    asyncio.run(agent.run("hello", consolidate=True))
    assert mem._episodic.count() == 1
    assert len(mem.working) == 2


def test_agent_bad_tool_arguments(tmp_config: Config) -> None:
    # Malformed JSON arguments must not crash the loop.
    tool_calls = [
        {"id": "c1", "type": "function", "function": {"name": "t", "arguments": "{not json"}}
    ]
    llm = FakeLLM(chat_tool_script=[(None, tool_calls), ("done", None)])
    mcp = FakeMCPToolServer(tools=[FakeTool("t")], results={"t": "result"})
    agent = Agent(_mem(tmp_config, llm), mcp=mcp)
    res = asyncio.run(agent.run("go", consolidate=False))
    assert res["reply"] == "done"
    assert mcp.calls == [("t", {})]
