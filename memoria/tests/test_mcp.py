import asyncio

from memoria.mcp.base import to_openai_tools
from memoria.mcp.fake import FakeMCPToolServer, FakeTool


def test_fake_mcp_list_and_call() -> None:
    tools = [FakeTool("maps_geo", "地理编码")]
    mcp = FakeMCPToolServer(
        tools=tools, results={"maps_geo": lambda args: f"coords for {args.get('address')}"}
    )
    listed = asyncio.run(mcp.list_tools())
    assert [t.name for t in listed] == ["maps_geo"]

    out = asyncio.run(mcp.call_tool_text("maps_geo", {"address": "北京南站"}))
    assert out == "coords for 北京南站"
    assert mcp.calls == [("maps_geo", {"address": "北京南站"})]


def test_to_openai_tools_shape() -> None:
    out = to_openai_tools([FakeTool("maps_weather", "天气查询")])
    assert out[0]["type"] == "function"
    assert out[0]["function"]["name"] == "maps_weather"
    assert out[0]["function"]["parameters"]["type"] == "object"


def test_to_openai_tools_empty() -> None:
    assert to_openai_tools([]) == []
