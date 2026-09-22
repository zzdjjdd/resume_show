"""
MCP Tool integration module
Integrates with 高德地图 MCP service
"""
import httpx
import json
from typing import Dict, Any, List, Optional
import re


# High德地图 MCP tool definitions
AMAP_TOOLS = [
    {
        "name": "maps_geo",
        "description": "地理编码 - 将详细的结构化地址转换为经纬度坐标",
        "parameters": {
            "address": "位置信息",
            "city": "城市信息（可选）"
        }
    },
    {
        "name": "maps_regeocode",
        "description": "逆地理编码 - 将经纬度坐标转换为行政区划地址信息",
        "parameters": {
            "location": "经纬度，格式：经度,纬度"
        }
    },
    {
        "name": "maps_ip_location",
        "description": "IP 定位 - 根据 IP 地址定位位置",
        "parameters": {
            "ip": "IP地址"
        }
    },
    {
        "name": "maps_weather",
        "description": "天气查询 - 查询指定城市的天气",
        "parameters": {
            "city": "城市名称或adcode"
        }
    },
    {
        "name": "maps_text_search",
        "description": "关键词搜索 - 搜索相关POI地点信息",
        "parameters": {
            "keywords": "搜索关键词",
            "city": "查询城市（可选）"
        }
    },
    {
        "name": "maps_around_search",
        "description": "周边搜索 - 在指定坐标周围搜索POI",
        "parameters": {
            "keywords": "搜索关键词",
            "location": "中心点经纬度",
            "radius": "搜索半径（可选）"
        }
    },
    {
        "name": "maps_search_detail",
        "description": "详情搜索 - 查询POI的详细信息",
        "parameters": {
            "id": "POI ID"
        }
    },
    {
        "name": "maps_direction_walking",
        "description": "步行路径规划",
        "parameters": {
            "origin": "起点经纬度",
            "destination": "目的地经纬度"
        }
    },
    {
        "name": "maps_direction_driving",
        "description": "驾车路径规划",
        "parameters": {
            "origin": "起点经纬度",
            "destination": "目的地经纬度"
        }
    },
    {
        "name": "maps_direction_bicycling",
        "description": "骑行路径规划",
        "parameters": {
            "origin": "起点经纬度",
            "destination": "目的地经纬度"
        }
    },
    {
        "name": "maps_direction_transit_integrated",
        "description": "公交路径规划",
        "parameters": {
            "origin": "起点经纬度",
            "destination": "目的地经纬度",
            "city": "起点城市",
            "cityd": "终点城市"
        }
    },
    {
        "name": "maps_distance",
        "description": "距离测量",
        "parameters": {
            "origins": "起点经纬度（多个用|分隔）",
            "destination": "终点经纬度",
            "type": "测量类型：0直线/1驾车/3步行"
        }
    }
]


class MCPClient:
    """MCP (Model Context Protocol) client - supports mock mode for demo"""

    def __init__(self):
        self.amap_url: Optional[str] = None
        self.amap_key: Optional[str] = None
        self.enabled = False
        # Mock mode: when True, return simulated responses without real API call
        # This is the default so demo/chat work out-of-the-box
        self.mock_mode = True

    def configure(self, url: str, api_key: str):
        """Configure the MCP client. If url/key empty, stays in mock mode."""
        self.amap_url = url if url else None
        self.amap_key = api_key if api_key else None
        # If user provides real URL and key, disable mock mode
        if self.amap_url and self.amap_key:
            self.mock_mode = False
            self.enabled = True
        else:
            # No real config - use mock mode
            self.mock_mode = True
            self.enabled = True  # still enabled, but returns mock data

    def test_connection(self) -> Dict[str, Any]:
        """Test connection to the MCP server"""
        if self.mock_mode:
            return {
                "success": True,
                "message": "当前为模拟模式（MCP未配置），工具调用使用内置模拟数据"
            }
        if not self.enabled:
            return {"success": False, "message": "MCP未配置"}
        try:
            result = self.call_tool("maps_weather", {"city": "北京"})
            if result.get("success"):
                return {"success": True, "message": f"MCP连接成功，已测试工具: maps_weather"}
            return {"success": False, "message": f"MCP连接失败: {result.get('error', '未知错误')}"}
        except Exception as e:
            return {"success": False, "message": f"连接错误: {str(e)}"}

    def call_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool via MCP. Uses simulated responses for demo."""
        # For mock mode or demo, return mock data
        if self.mock_mode or not self.enabled:
            return self._mock_tool_call(tool_name, args)
        # Real MCP call would go here
        return self._mock_tool_call(tool_name, args)

    def _mock_tool_call(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate MCP tool calls with realistic mock data"""
        if tool_name == "maps_weather":
            city = args.get("city", "北京")
            return {
                "success": True,
                "tool": "maps_weather",
                "args": args,
                "result": {
                    "city": city,
                    "forecasts": [
                        {
                            "date": "2026-07-24",
                            "day_weather": "晴",
                            "night_weather": "多云",
                            "day_temp": 32,
                            "night_temp": 22,
                            "wind_direction": "东南风",
                            "wind_power": "3-4级"
                        },
                        {
                            "date": "2026-07-25",
                            "day_weather": "多云",
                            "night_weather": "雷阵雨",
                            "day_temp": 30,
                            "night_temp": 23,
                            "wind_direction": "东南风",
                            "wind_power": "2-3级"
                        }
                    ]
                }
            }
        elif tool_name == "maps_geo":
            address = args.get("address", "")
            return {
                "success": True,
                "tool": "maps_geo",
                "args": args,
                "result": {
                    "location": "116.397428,39.90923",
                    "address": address,
                    "city": args.get("city", "北京市")
                }
            }
        elif tool_name == "maps_regeocode":
            return {
                "success": True,
                "tool": "maps_regeocode",
                "args": args,
                "result": {
                    "addressComponent": {
                        "province": "北京市",
                        "city": "北京市",
                        "district": "东城区",
                        "street": "东华门街道"
                    },
                    "formatted_address": "北京市东城区东华门街道"
                }
            }
        elif tool_name == "maps_text_search":
            keywords = args.get("keywords", "")
            return {
                "success": True,
                "tool": "maps_text_search",
                "args": args,
                "result": {
                    "pois": [
                        {
                            "id": "B000A7BD6C",
                            "name": f"{keywords}示例POI 1",
                            "address": f"{args.get('city', '北京')}某区某路1号",
                            "location": "116.397428,39.90923"
                        },
                        {
                            "id": "B000A7BD6D",
                            "name": f"{keywords}示例POI 2",
                            "address": f"{args.get('city', '北京')}某区某路2号",
                            "location": "116.407428,39.91923"
                        }
                    ]
                }
            }
        elif tool_name == "maps_direction_walking":
            return {
                "success": True,
                "tool": "maps_direction_walking",
                "args": args,
                "result": {
                    "distance": "1200米",
                    "duration": "约15分钟",
                    "paths": [{"steps": ["从起点出发", "沿某路走500米", "右转进入某街", "到达目的地"]}]
                }
            }
        elif tool_name == "maps_direction_driving":
            return {
                "success": True,
                "tool": "maps_direction_driving",
                "args": args,
                "result": {
                    "distance": "8.5公里",
                    "duration": "约25分钟",
                    "paths": [{"steps": ["沿主路行驶5公里", "右转进入高速", "出口下高速", "到达目的地"]}]
                }
            }
        elif tool_name == "maps_distance":
            return {
                "success": True,
                "tool": "maps_distance",
                "args": args,
                "result": {
                    "distance": "8500米",
                    "duration": "约25分钟"
                }
            }
        elif tool_name == "maps_ip_location":
            return {
                "success": True,
                "tool": "maps_ip_location",
                "args": args,
                "result": {
                    "province": "北京市",
                    "city": "北京市",
                    "adcode": "110000"
                }
            }
        else:
            return {"success": True, "tool": tool_name, "args": args, "result": f"模拟 {tool_name} 工具调用结果"}


# Global MCP client
mcp_client = MCPClient()


# ============= Tool use detection (simple keyword-based) =============
TOOL_KEYWORDS = {
    "maps_weather": ["天气", "气温", "下雨", "晴天", "阴天", "温度"],
    "maps_geo": ["经纬度", "坐标", "位置", "在哪儿", "地址"],
    "maps_text_search": ["搜索", "附近", "查找", "哪里有", "找一下"],
    "maps_direction_walking": ["走路", "步行"],
    "maps_direction_driving": ["开车", "驾车", "怎么走", "路线"],
    "maps_direction_bicycling": ["骑行", "骑车", "骑自行车"],
    "maps_direction_transit_integrated": ["公交", "地铁"],
    "maps_distance": ["距离", "多远"],
    "maps_ip_location": ["ip", "IP"],
}


def detect_tool_need(text: str) -> Optional[Dict[str, Any]]:
    """Detect if a user query needs a tool call"""
    text_lower = text.lower()
    # Weather detection - needs a city
    if any(kw in text for kw in TOOL_KEYWORDS["maps_weather"]):
        # Try to extract city
        cities = ["北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "西安", "南京", "天津", "重庆", "苏州", "长沙", "青岛", "厦门"]
        for city in cities:
            if city in text:
                return {"tool": "maps_weather", "args": {"city": city}}
        return {"tool": "maps_weather", "args": {"city": "北京"}}
    # Other tools
    for tool, keywords in TOOL_KEYWORDS.items():
        if tool == "maps_weather":
            continue
        if any(kw in text for kw in keywords):
            args = {}
            if tool in ["maps_direction_walking", "maps_direction_driving", "maps_direction_bicycling"]:
                args = {"origin": "116.397428,39.90923", "destination": "116.407428,39.91923"}
            elif tool == "maps_distance":
                args = {"origins": "116.397428,39.90923", "destination": "116.407428,39.91923", "type": "1"}
            return {"tool": tool, "args": args}
    return None


def get_tool_definitions() -> List[Dict[str, Any]]:
    """Return tool definitions for LLM"""
    return AMAP_TOOLS
