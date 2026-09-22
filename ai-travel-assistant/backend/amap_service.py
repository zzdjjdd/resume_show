"""
高德地图开放接口封装层。
当用户在前端配置了高德 API Key 后，本模块负责真正调用高德开放平台：
- 地理编码 / 逆地理编码
- 天气查询
- 关键词 / 周边 POI 搜索
- 驾车 / 步行 / 公交 / 骑行 路径规划
- 距离测量
它们将以 MCP 工具的形式被 LLM 在聊天模式下调用。
"""
import json
import urllib.parse
from typing import Any, Dict, List, Optional

import requests

AMAP_BASE = "https://restapi.amap.com/v3"


class AmapError(Exception):
    pass


def _amap_get(path: str, params: Dict[str, Any], key: str, timeout: int = 8) -> Dict[str, Any]:
    if not key:
        raise AmapError("未配置高德地图 API Key，无法调用地图服务")
    qp = {"key": key, "output": "JSON"}
    qp.update({k: v for k, v in params.items() if v not in (None, "")})
    url = f"{AMAP_BASE}/{path}?{urllib.parse.urlencode(qp)}"
    try:
        r = requests.get(url, timeout=timeout)
    except requests.RequestException as e:
        raise AmapError(f"网络异常: {e}")
    try:
        data = r.json()
    except ValueError:
        raise AmapError("返回非 JSON 数据")
    if str(data.get("status")) != "1":
        raise AmapError(data.get("info") or data.get("infocode") or "调用失败")
    return data


# ---------------- 工具实现 ----------------

def geocode(address: str, city: Optional[str], key: str) -> Dict[str, Any]:
    """地理编码：地址 -> 经纬度"""
    data = _amap_get("geocode/geo", {"address": address, "city": city}, key)
    geocodes = data.get("geocodes") or []
    if not geocodes:
        raise AmapError("未找到该地址")
    g = geocodes[0]
    loc = g.get("location", "")
    formatted = g.get("formatted_address") or address
    return {"location": loc, "address": formatted, "city": g.get("city")}


def regeocode(location: str, key: str) -> Dict[str, Any]:
    """逆地理编码：经纬度 -> 地址"""
    data = _amap_get("geocode/regeo", {"location": location, "extensions": "base"}, key)
    rc = data.get("regeocode") or {}
    ac = rc.get("addressComponent") or {}
    return {
        "address": rc.get("formatted_address"),
        "province": ac.get("province"),
        "city": (ac.get("city") or ac.get("province")),
        "district": ac.get("district"),
        "adcode": ac.get("adcode"),
        "township": ac.get("township"),
    }


def weather(city: str, key: str) -> Dict[str, Any]:
    """天气查询"""
    data = _amap_get("weather/weatherInfo", {"city": city, "extensions": "all"}, key)
    return {"city": city, "forecasts": data.get("forecasts") or []}


def text_search(keywords: str, city: Optional[str], key: str) -> List[Dict[str, Any]]:
    """关键词搜索 POI"""
    data = _amap_get("place/text", {"keywords": keywords, "city": city, "citylimit": "true" if city else "false"}, key)
    pois = data.get("pois") or []
    return [
        {
            "id": p.get("id"),
            "name": p.get("name"),
            "address": p.get("address"),
            "location": p.get("location"),
            "type": p.get("type"),
            "tel": p.get("tel"),
        }
        for p in pois[:10]
    ]


def around_search(keywords: str, location: str, radius: int, key: str) -> List[Dict[str, Any]]:
    """周边搜索"""
    data = _amap_get(
        "place/around",
        {"keywords": keywords, "location": location, "radius": radius},
        key,
    )
    pois = data.get("pois") or []
    return [
        {
            "id": p.get("id"),
            "name": p.get("name"),
            "address": p.get("address"),
            "location": p.get("location"),
            "distance": p.get("distance"),
        }
        for p in pois[:10]
    ]


def route_driving(origin: str, destination: str, key: str) -> Dict[str, Any]:
    """驾车路径规划"""
    data = _amap_get("direction/driving", {"origin": origin, "destination": destination, "extensions": "base"}, key)
    path = (data.get("route") or {}).get("paths") or []
    if not path:
        return {"distance": 0, "duration": 0, "steps": []}
    p = path[0]
    return {
        "distance": int(p.get("distance", 0)),
        "duration": int((p.get("duration") or "0").split(".")[0]),
        "steps": [
            {"instruction": s.get("instruction"), "road": s.get("road"), "distance": int(s.get("distance", 0))}
            for s in (p.get("steps") or [])[:20]
        ],
    }


def route_walking(origin: str, destination: str, key: str) -> Dict[str, Any]:
    data = _amap_get("direction/walking", {"origin": origin, "destination": destination}, key)
    path = (data.get("route") or {}).get("paths") or []
    if not path:
        return {"distance": 0, "duration": 0, "steps": []}
    p = path[0]
    return {
        "distance": int(p.get("distance", 0)),
        "duration": int((p.get("duration") or "0").split(".")[0]),
        "steps": [s.get("instruction") for s in (p.get("steps") or [])[:20]],
    }


def route_transit(origin: str, destination: str, city: str, cityd: str, key: str) -> Dict[str, Any]:
    data = _amap_get(
        "direction/transit/integrated",
        {"origin": origin, "destination": destination, "city": city, "cityd": cityd},
        key,
    )
    return {
        "distance": int((data.get("route") or {}).get("distance", 0) or 0),
        "transits": [
            {
                "duration": int(((t.get("duration") or "0").split(".")[0])),
                "walking_distance": int(t.get("walking_distance", 0) or 0),
                "segments": [
                    {
                        "mode": (seg.get("transit_mode") or "WALKING"),
                        "line_name": ((seg.get("transit") or {}).get("linename")),
                        "station_names": ((seg.get("transit") or {}).get("stationnames")),
                    }
                    for seg in (t.get("segments") or [])
                ],
            }
            for t in ((data.get("route") or {}).get("transits") or [])[:5]
        ],
    }


def distance_measure(origin: str, destination: str, key: str) -> Dict[str, Any]:
    data = _amap_get("distance", {"origins": origin, "destination": destination, "type": 1}, key)
    res = (data.get("results") or [{}])[0]
    return {
        "origin_id": res.get("origin_id"),
        "dest_id": res.get("dest_id"),
        "distance": int(res.get("distance", 0)),
        "duration": int(res.get("duration", 0)),
    }


# ---------------- MCP 工具注册表 ----------------

MCP_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "amap_geocode",
            "description": "将结构化地址转换为高德地图经纬度坐标，例如 '北京·中关村' → '116.310,39.985'",
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {"type": "string", "description": "待解析的地址"},
                    "city": {"type": "string", "description": "城市范围，可选"},
                },
                "required": ["address"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "amap_regeocode",
            "description": "把经纬度坐标转换为行政区划与地址",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "经度,纬度，例如 116.31,39.98"},
                },
                "required": ["location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "amap_weather",
            "description": "查询指定城市的天气预报",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string", "description": "城市名或 adcode"}},
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "amap_text_search",
            "description": "根据关键词搜索 POI 地点，例如搜索景点、餐饮、酒店",
            "parameters": {
                "type": "object",
                "properties": {
                    "keywords": {"type": "string", "description": "搜索关键词"},
                    "city": {"type": "string", "description": "限制城市，可选"},
                },
                "required": ["keywords"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "amap_around_search",
            "description": "在指定坐标附近搜索 POI",
            "parameters": {
                "type": "object",
                "properties": {
                    "keywords": {"type": "string"},
                    "location": {"type": "string", "description": "中心经度,纬度"},
                    "radius": {"type": "integer", "description": "搜索半径（米），默认 1000"},
                },
                "required": ["keywords", "location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "amap_route_driving",
            "description": "规划两地之间的驾车路线",
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
            "name": "amap_route_walking",
            "description": "规划两地之间的步行路线",
            "parameters": {
                "type": "object",
                "properties": {"origin": {"type": "string"}, "destination": {"type": "string"}},
                "required": ["origin", "destination"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "amap_route_transit",
            "description": "规划两地之间的公共交通（地铁/公交）路线",
            "parameters": {
                "type": "object",
                "properties": {
                    "origin": {"type": "string"},
                    "destination": {"type": "string"},
                    "city": {"type": "string"},
                    "cityd": {"type": "string"},
                },
                "required": ["origin", "destination", "city", "cityd"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "amap_distance",
            "description": "测量两个经纬度之间的距离和通行时间",
            "parameters": {
                "type": "object",
                "properties": {"origin": {"type": "string"}, "destination": {"type": "string"}},
                "required": ["origin", "destination"],
            },
        },
    },
]


def run_tool(name: str, args: Dict[str, Any], key: str) -> Dict[str, Any]:
    """工具分发：根据 name 调用对应高德接口。失败不会抛异常，便于在聊天中显示错误。"""
    try:
        if name == "amap_geocode":
            return geocode(args.get("address", ""), args.get("city"), key)
        if name == "amap_regeocode":
            return regeocode(args.get("location", ""), key)
        if name == "amap_weather":
            return weather(args.get("city", ""), key)
        if name == "amap_text_search":
            return {"pois": text_search(args.get("keywords", ""), args.get("city"), key)}
        if name == "amap_around_search":
            return {"pois": around_search(args.get("keywords", ""), args.get("location", ""), int(args.get("radius") or 1000), key)}
        if name == "amap_route_driving":
            return route_driving(args.get("origin", ""), args.get("destination", ""), key)
        if name == "amap_route_walking":
            return route_walking(args.get("origin", ""), args.get("destination", ""), key)
        if name == "amap_route_transit":
            return route_transit(args.get("origin", ""), args.get("destination", ""), args.get("city", ""), args.get("cityd", ""), key)
        if name == "amap_distance":
            return distance_measure(args.get("origin", ""), args.get("destination", ""), key)
        return {"error": f"未知工具: {name}"}
    except AmapError as e:
        return {"error": str(e), "tool": name}
    except Exception as e:  # noqa: BLE001
        return {"error": f"工具执行失败: {e}", "tool": name}
