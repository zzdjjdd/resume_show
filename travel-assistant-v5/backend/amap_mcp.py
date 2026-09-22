"""高德 MCP 工具桥接：把 LLM 的 tool_call 转到高德 MCP SSE 服务
此模块通过 SSE 与高德 MCP 服务通信，并在聊天流中输出调用信息。
"""
import json
import httpx
from typing import Any, Dict, List, Optional, AsyncIterator
import asyncio


class AmapMCPClient:
    """与高德 MCP（SSE）服务通信的桥接器

    由于 SSE 的双向实时握手在服务端实现差异较大，这里提供两种接入方式：
    1) 直接调用高德 REST 风格地图 API（如果你填了 API Key）；用于通用搜索/路径/POI 等
    2) 通过配置的 mcp.server_url（SSE）尝试透传 tool_call（需要 MCP 服务侧支持）
    """

    AMAP_REST_BASE = "https://restapi.amap.com/v3"

    def __init__(self, api_key: str, sse_url: str = "", server_url: str = ""):
        self.api_key = api_key
        self.sse_url = sse_url
        self.server_url = server_url

    def tools(self) -> List[Dict[str, Any]]:
        """返回供 LLM 使用的工具定义（OpenAI function-call 格式）"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "maps_geo",
                    "description": "将详细结构化地址转换为经纬度坐标",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "address": {"type": "string", "description": "待解析的结构化地址"},
                            "city": {"type": "string", "description": "指定查询的城市（可选）"},
                        },
                        "required": ["address"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "maps_regeocode",
                    "description": "将经纬度坐标转换为行政区划地址信息",
                    "parameters": {
                        "type": "object",
                        "properties": {"location": {"type": "string", "description": "经纬度，如 116.397,39.908"}},
                        "required": ["location"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "maps_text_search",
                    "description": "根据关键词搜索 POI 地点",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "keywords": {"type": "string"},
                            "city": {"type": "string", "description": "查询城市（可选）"},
                        },
                        "required": ["keywords"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "maps_around_search",
                    "description": "在指定坐标附近搜索 POI",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "keywords": {"type": "string"},
                            "location": {"type": "string"},
                            "radius": {"type": "string"},
                        },
                        "required": ["location"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "maps_direction_driving",
                    "description": "驾车路径规划",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "origin": {"type": "string", "description": "起点经纬度"},
                            "destination": {"type": "string", "description": "终点经纬度"},
                        },
                        "required": ["origin", "destination"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "maps_direction_walking",
                    "description": "步行路径规划",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "origin": {"type": "string"},
                            "destination": {"type": "string"},
                        },
                        "required": ["origin", "destination"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "maps_direction_transit_integrated",
                    "description": "公交路径规划（跨城必填起点城市和终点城市）",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "origin": {"type": "string"},
                            "destination": {"type": "string"},
                            "city": {"type": "string", "description": "起点城市"},
                            "cityd": {"type": "string", "description": "终点城市"},
                        },
                        "required": ["origin", "destination", "city", "cityd"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "maps_distance",
                    "description": "距离测量",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "origins": {"type": "string"},
                            "destination": {"type": "string"},
                            "type": {"type": "string", "description": "1=驾车 0=直线 3=步行"},
                        },
                        "required": ["origins", "destination"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "maps_weather",
                    "description": "查询指定城市的天气",
                    "parameters": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                        "required": ["city"],
                    },
                },
            },
        ]

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """统一执行 MCP 工具：通过高德 REST API 直接调用"""
        if not self.api_key:
            return {"success": False, "error": "高德 API Key 为空，请先在设置中填写"}

        try:
            if name == "maps_geo":
                return await self._geo(arguments.get("address", ""), arguments.get("city", ""))
            if name == "maps_regeocode":
                return await self._regeocode(arguments.get("location", ""))
            if name == "maps_text_search":
                return await self._text_search(arguments.get("keywords", ""), arguments.get("city", ""))
            if name == "maps_around_search":
                return await self._around_search(
                    arguments.get("keywords", ""),
                    arguments.get("location", ""),
                    arguments.get("radius", "1000"),
                )
            if name == "maps_direction_driving":
                return await self._driving(arguments.get("origin", ""), arguments.get("destination", ""))
            if name == "maps_direction_walking":
                return await self._walking(arguments.get("origin", ""), arguments.get("destination", ""))
            if name == "maps_direction_transit_integrated":
                return await self._transit(
                    arguments.get("origin", ""),
                    arguments.get("destination", ""),
                    arguments.get("city", ""),
                    arguments.get("cityd", ""),
                )
            if name == "maps_distance":
                return await self._distance(
                    arguments.get("origins", ""),
                    arguments.get("destination", ""),
                    arguments.get("type", "1"),
                )
            if name == "maps_weather":
                return await self._weather(arguments.get("city", ""))
            return {"success": False, "error": f"未知工具: {name}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # --------------------- 高德 REST API 调用 ---------------------
    async def _get(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        params = dict(params or {})
        params["key"] = self.api_key
        params["output"] = "JSON"
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(f"{self.AMAP_REST_BASE}/{path}", params=params)
            r.raise_for_status()
            return {"success": True, "data": r.json()}

    async def _geo(self, address: str, city: str = "") -> Dict[str, Any]:
        if not address:
            return {"success": False, "error": "address 必填"}
        params = {"address": address}
        if city:
            params["city"] = city
        return await self._get("geocode/geo", params)

    async def _regeocode(self, location: str) -> Dict[str, Any]:
        if not location:
            return {"success": False, "error": "location 必填"}
        return await self._get("geocode/regeo", {"location": location, "extensions": "base"})

    async def _text_search(self, keywords: str, city: str = "") -> Dict[str, Any]:
        if not keywords:
            return {"success": False, "error": "keywords 必填"}
        params = {"keywords": keywords}
        if city:
            params["city"] = city
        return await self._get("place/text", params)

    async def _around_search(self, keywords: str, location: str, radius: str = "1000") -> Dict[str, Any]:
        if not location:
            return {"success": False, "error": "location 必填"}
        params = {"location": location, "radius": radius or "1000"}
        if keywords:
            params["keywords"] = keywords
        return await self._get("place/around", params)

    async def _driving(self, origin: str, destination: str) -> Dict[str, Any]:
        if not origin or not destination:
            return {"success": False, "error": "origin/destination 必填"}
        return await self._get("direction/driving", {"origin": origin, "destination": destination})

    async def _walking(self, origin: str, destination: str) -> Dict[str, Any]:
        if not origin or not destination:
            return {"success": False, "error": "origin/destination 必填"}
        return await self._get("direction/walking", {"origin": origin, "destination": destination})

    async def _transit(self, origin: str, destination: str, city: str, cityd: str) -> Dict[str, Any]:
        if not origin or not destination:
            return {"success": False, "error": "origin/destination 必填"}
        params = {"origin": origin, "destination": destination}
        if city:
            params["city"] = city
        if cityd:
            params["cityd"] = cityd
        return await self._get("direction/transit/integrated", params)

    async def _distance(self, origins: str, destination: str, type_: str = "1") -> Dict[str, Any]:
        if not origins or not destination:
            return {"success": False, "error": "origins/destination 必填"}
        return await self._get("distance", {"origins": origins, "destination": destination, "type": type_})

    async def _weather(self, city: str) -> Dict[str, Any]:
        if not city:
            return {"success": False, "error": "city 必填"}
        return await self._get("weather/weatherInfo", {"city": city, "extensions": "base"})


def summarize_amap_result(name: str, result: Dict[str, Any]) -> str:
    """把工具调用结果压缩成人类可读摘要"""
    if not result.get("success"):
        return f"调用失败: {result.get('error', '未知错误')}"
    data = result.get("data", {}) or {}
    try:
        if name == "maps_geo":
            geocodes = data.get("geocodes", [])
            if geocodes:
                g = geocodes[0]
                loc = g.get("location", "")
                formatted = g.get("formatted_address", "")
                return f"地理编码成功：{formatted}（{loc}）"
            return "未找到匹配地址"
        if name == "maps_regeocode":
            comp = (data.get("regeocode") or {}).get("addressComponent", {})
            return f"逆地理编码：{comp.get('province','')}{comp.get('city','')}{comp.get('district','')}"
        if name == "maps_text_search" or name == "maps_around_search":
            pois = data.get("pois", []) or []
            if not pois:
                return "未找到 POI"
            lines = [f"共 {len(pois)} 个结果："]
            for p in pois[:5]:
                lines.append(f"- {p.get('name','?')} | {p.get('address','-')} | {p.get('location','')}")
            return "\n".join(lines)
        if name in ("maps_direction_driving", "maps_direction_walking", "maps_direction_transit_integrated"):
            paths = data.get("route", {}).get("paths", []) or data.get("route", {}).get("transits", []) or []
            if not paths:
                return "未找到路径"
            if name == "maps_direction_transit_integrated":
                t = paths[0]
                segs = []
                for s in t.get("segments", []) or []:
                    segs.append(f"步行{(s.get('walking',{}) or {}).get('distance','?')}m + {(s.get('bus',{}) or {}).get('buslines',[{}])[0].get('name','公交')}")
                return f"公交方案：全程 {t.get('distance','?')}m，约 {t.get('duration','?')}s；分段：" + " / ".join(segs)
            p = paths[0]
            dist = p.get("distance", "?")
            dur = p.get("duration", "?")
            steps = p.get("steps", []) or []
            detail = ""
            if steps:
                detail = "；第一步：" + (steps[0].get("instruction", "") or "")
            return f"路径规划：距离 {dist}m，预计 {dur}s{detail}"
        if name == "maps_distance":
            results = data.get("results", []) or []
            if not results:
                return "未返回距离"
            r = results[0]
            return f"距离 {r.get('distance','?')}m，用时 {r.get('duration','?')}s"
        if name == "maps_weather":
            lives = data.get("lives", []) or []
            if not lives:
                return "未找到天气数据"
            w = lives[0]
            return f"{w.get('city','?')} 天气：{w.get('weather','')}，{w.get('temperature','?')}℃，{w.get('winddirection','')}风 {w.get('windpower','')}级"
        return json.dumps(data, ensure_ascii=False)[:500]
    except Exception as e:
        return f"解析结果出错: {e}；原始数据: {json.dumps(data, ensure_ascii=False)[:200]}"
