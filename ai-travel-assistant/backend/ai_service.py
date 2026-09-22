"""
AI 服务层：负责调用可配置的 OpenAI 兼容 LLM，提供两类能力：
1. chat_stream：聊天模式（多轮 + 工具调用 + 流式输出 + 工具结果回传）
2. generate_travel_plan：旅游模式（一次性生成 Markdown 行程计划）

默认走本地环境变量驱动的 MiniMax-M3：
- api_key / base_url 为空时直接 OpenAI()，由 SDK 读 OPENAI_API_KEY / OPENAI_BASE_URL
- 调用时附带 extra_body={"reasoning_split": True}（见 minmax模型使用说明.md），
  服务端会把思考过程放到 response.choices[0].message.reasoning_details 中。

ReAct 事件约定（chat_stream 增量产出，前端按"阶段 + 步骤"构建可折叠思考面板）：
  type="step",  phase="begin" | "delta" | "end",
  step ∈ {thought, intent, tool_select, args, action, observation, iterate},
  其它字段：title / icon / content / data。
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, Generator, List, Optional

from openai import OpenAI, OpenAIError

from . import amap_service, mcp_client
from .config import load_config

logger = logging.getLogger(__name__)


# ---------------- ReAct 步骤元数据 ----------------
# 前端拿到 step 名就能查到对应的中文标题和图标，避免两边各自维护。
STEP_META: Dict[str, Dict[str, str]] = {
    "thought":      {"title": "思考",     "icon": "🧠"},
    "intent":       {"title": "意图识别", "icon": "🎯"},
    "tool_select":  {"title": "选择工具", "icon": "🔧"},
    "args":         {"title": "构造参数", "icon": "📦"},
    "action":       {"title": "执行调用", "icon": "⚡"},
    "observation":  {"title": "观察结果", "icon": "👁️"},
    "iterate":      {"title": "迭代判断", "icon": "🔄"},
}

# ---------------- 旅游模式步骤元数据 ----------------
TRAVEL_STEPS: Dict[str, Dict[str, str]] = {
    "prepare":   {"title": "准备参数", "icon": "📋"},
    "geocode":   {"title": "解析坐标", "icon": "📍"},
    "route":     {"title": "测算路线", "icon": "🚗"},
    "weather":   {"title": "查询天气", "icon": "🌤️"},
    "ai":        {"title": "AI 规划", "icon": "🤖"},
    "integrate": {"title": "整合结果", "icon": "✨"},
}


def _travel_step(step: str, phase: str, **fields: Any) -> Dict[str, Any]:
    """构造旅游模式 step 事件。"""
    meta = TRAVEL_STEPS.get(step, {"title": step, "icon": "•"})
    evt: Dict[str, Any] = {
        "type": "step",
        "phase": phase,
        "step": step,
        "title": meta["title"],
        "icon": meta["icon"],
    }
    evt.update(fields)
    return evt


def _step_event(step: str, phase: str, **fields: Any) -> Dict[str, Any]:
    """构造一个 step 事件，自动补齐 title/icon。"""
    meta = STEP_META.get(step, {"title": step, "icon": "•"})
    evt: Dict[str, Any] = {
        "type": "step",
        "phase": phase,  # begin | delta | end
        "step": step,
        "title": meta["title"],
        "icon": meta["icon"],
    }
    evt.update(fields)
    return evt


def _intent_from_messages(messages: List[Dict[str, Any]], reasoning: str) -> str:
    """从最近一条 user 消息 + reasoning 中提炼一句"意图识别"。
    之所以本地完成：避免为这一小步多发一次 LLM 调用。
    """
    last_user = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user = (m.get("content") or "").strip()
            break

    snippet = (reasoning or "").strip()
    if snippet:
        # 取 reasoning 的第一句作为意图描述
        first_sentence = re.split(r"[。！？!?\n]", snippet, maxsplit=1)[0].strip()
        if first_sentence:
            base = first_sentence[:120]
        else:
            base = ""
    else:
        base = ""

    if last_user and base:
        return f"用户提问：「{last_user[:60]}」 → 推断意图：{base}"
    if last_user:
        return f"用户提问：「{last_user[:80]}」，需要结合上下文给出回应。"
    return "综合历史对话继续回答用户。"


def _summarize_tool_result(name: str, result: Dict[str, Any]) -> str:
    """把工具返回值压缩成一句人话，让观察步骤不至于把 JSON 全文贴出来。"""
    if not isinstance(result, dict):
        return str(result)[:160]
    if "error" in result:
        err = result["error"]
        if name.startswith("12306__"):
            return f"12306 MCP 错误：{err}"
        if name.startswith("hotel__"):
            return f"酒店 MCP 错误：{err}"
        return f"工具返回错误：{err}"
    # 外部 MCP 工具（name 含 "__"）：按 server 兜底摘要
    if "__" in name:
        server = name.split("__", 1)[0]
        content = result.get("content")
        if isinstance(content, list) and content and isinstance(content[0], dict):
            text = content[0].get("text", "")
            return f"已调用 {server} MCP：{str(text)[:120]}"
        if isinstance(content, str):
            return f"已调用 {server} MCP：{content[:120]}"
        return f"已调用 {server} MCP 工具 {name.split('__', 1)[1]} 完成。"
    if name == "amap_geocode":
        return f"地理编码得到：{result.get('address')}（{result.get('location')}）"
    if name == "amap_regeocode":
        return f"逆编码得到：{result.get('address')}（{result.get('city')}）"
    if name == "amap_weather":
        casts = ((result.get("forecasts") or [{}])[0]).get("casts") or []
        if casts:
            c = casts[0]
            return f"{result.get('city')} 天气：白天 {c.get('dayweather')} {c.get('daytemp')}°C / 夜间 {c.get('nightweather')} {c.get('nighttemp')}°C"
        return "已获取天气数据。"
    if name in ("amap_text_search", "amap_around_search"):
        pois = result.get("pois") or []
        if not pois:
            return "未搜索到 POI。"
        top = ", ".join(p.get("name", "?") for p in pois[:3])
        return f"命中 {len(pois)} 个 POI，前三位：{top}"
    if name in ("amap_route_driving", "amap_route_walking", "amap_route_transit"):
        dist_km = result.get("distance", 0) / 1000.0
        dur_min = result.get("duration", 0) / 60.0
        return f"规划完成：约 {dist_km:.1f} km / {dur_min:.1f} 分钟"
    if name == "amap_distance":
        return f"两点相距 {result.get('distance', 0)} 米，预计通行 {result.get('duration', 0)} 秒"
    return f"已获得 {name} 的结果。"


def _build_http_client(timeout: float = 60.0):
    """显式构造 httpx.Client，避免 openai 1.13.3 自带的 SyncHttpxClientWrapper
    把废弃的 `proxies=` 关键字传给 httpx 0.28+（后者已只接受 `proxy` 单数）。
    """
    import httpx
    return httpx.Client(timeout=timeout, follow_redirects=True)


def _client() -> OpenAI:
    """构造 OpenAI 客户端。

    - 若用户已配置 api_key/base_url：使用对应值实例化
    - 若都为空：调用 OpenAI() 不带参数，由其读环境变量（与官方示例一致）
    - 总是显式传入 http_client，避免 openai 内部用废弃 proxies= 构造 httpx
    """
    cfg = load_config()
    llm = cfg.get("llm") or {}
    api_key = (llm.get("api_key") or "").strip()
    base_url = (llm.get("base_url") or "").strip()

    kwargs: Dict[str, Any] = {"http_client": _build_http_client()}
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["base_url"] = base_url

    return OpenAI(**kwargs)


def _extra_body(cfg_llm: Dict[str, Any]) -> Dict[str, Any]:
    """根据配置构造 extra_body。"""
    if cfg_llm.get("reasoning_split", True):
        return {"reasoning_split": True}
    return {}


def test_connection() -> Dict[str, Any]:
    """测试 LLM 连通性（用一次极简请求）"""
    cfg = load_config()
    llm = cfg.get("llm") or {}
    model = llm.get("model") or "MiniMax-M3"
    try:
        cli = _client()
        t0 = time.time()
        resp = cli.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
            extra_body=_extra_body(llm),
        )
        cost = round((time.time() - t0) * 1000, 1)
        return {"ok": True, "message": f"连接成功（{cost} ms，模型 {model}）", "model": model}
    except OpenAIError as e:
        return {"ok": False, "message": f"LLM 调用失败：{e}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": f"连接失败：{e}"}


def test_amap_connection() -> Dict[str, Any]:
    """测试高德地图：使用配置的 Key 调用地理编码接口。"""
    cfg = load_config()
    api_key = (cfg.get("amap") or {}).get("api_key") or ""
    if not api_key.strip():
        return {"ok": False, "message": "尚未配置 API Key"}
    try:
        data = amap_service.geocode("北京天安门", "北京", api_key)
        return {"ok": True, "message": f"连接成功（示例解析到：{data.get('address')}）"}
    except amap_service.AmapError as e:
        return {"ok": False, "message": f"高德接口失败：{e}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": f"连接失败：{e}"}


# ---------------- 聊天（带工具调用 + 流式） ----------------

def _ensure_tools() -> List[Dict[str, Any]]:
    """合并本地 amap 工具与外部 MCP server 声明的工具。
    外部 MCP 工具名形如 "{server_name}__{tool_name}"，分发时按 `__` 拆分。
    """
    amap_tools = amap_service.MCP_TOOLS or []
    try:
        mcp_tools, _ = mcp_client.load_mcp_tools()
    except Exception as e:  # noqa: BLE001
        logger.warning("[ai_service] 加载 MCP 工具失败：%s", e)
        mcp_tools = []
    return list(amap_tools) + list(mcp_tools or [])


SYSTEM_PROMPT = """你是「AI智行助手」，一名贴心的中文智能出行助手。
你可以：
1) 通过工具调用获取真实的地理、天气、POI、路线数据；
2) 在对话中把工具的原始数据以「📍 工具结果 · {工具名}」的可读格式摘要展示给用户；
3) 基于工具结果，再用自然语言给出建议、行程规划、出行贴士。

你也可以通过 MCP 调用用户已在「设置」中配置的外部 server（如 12306 火车票查询、酒店搜索）。
外部 MCP 工具名形如 "{server_name}__{tool_name}"，调用结果中带 `server` 字段标识来源。

风格：温暖、专业、简洁；用 Markdown 列表/小标题组织长答案；交通/位置相关数据务必依据工具，禁止瞎编。"""


def chat_stream(
    messages: List[Dict[str, Any]],
    *,
    tool_events: Optional[Any] = None,
) -> Generator[Dict[str, Any], None, None]:
    """
    流式聊天：yield {"type": "delta|thinking|tool|step|done|error", ...}
    其中 type="step" 为 ReAct 各阶段的事件（begin/delta/end）。
    """
    cfg = load_config()
    llm = cfg.get("llm") or {}
    amap_key = ((cfg.get("amap") or {}).get("api_key") or "").strip()

    try:
        cli = _client()
    except Exception as e:  # noqa: BLE001
        yield {"type": "error", "message": f"无法初始化客户端：{e}"}
        return

    model = llm.get("model") or "MiniMax-M3"
    extra_body = _extra_body(llm)

    history: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}] + list(messages)

    # 最多 5 轮工具调用循环
    for _round in range(5):
        # ---- ReAct Step 1: 思考（begin）----
        yield _step_event("thought", "begin")

        try:
            stream = cli.chat.completions.create(
                model=model,
                messages=history,
                tools=_ensure_tools() if amap_key else None,
                tool_choice="auto" if amap_key else "none",
                stream=True,
                temperature=0.7,
                extra_body=extra_body,
            )
        except OpenAIError as e:
            yield _step_event("thought", "end", summary=f"LLM 错误：{e}", status="error")
            yield {"type": "error", "message": f"LLM 错误：{e}"}
            return
        except Exception as e:  # noqa: BLE001
            yield _step_event("thought", "end", summary=f"网络错误：{e}", status="error")
            yield {"type": "error", "message": f"网络错误：{e}"}
            return

        content_buf = ""
        reasoning_buf = ""
        tool_calls: List[Dict[str, Any]] = []
        finish_reason = None
        first_chunk = True

        for chunk in stream:
            try:
                choice = chunk.choices[0]
            except (IndexError, AttributeError):
                continue
            delta = choice.delta
            if getattr(delta, "content", None):
                content_buf += delta.content
                yield {"type": "delta", "content": delta.content}
            # 兼容 reasoning_content（旧式）与 reasoning_details 字段
            rc = getattr(delta, "reasoning_content", None)
            if rc:
                reasoning_buf += rc
                yield _step_event("thought", "delta", content=rc)
                if first_chunk:
                    first_chunk = False
            rd = getattr(delta, "reasoning_details", None)
            if rd:
                for item in rd:
                    text = item.get("text") if isinstance(item, dict) else None
                    if text:
                        reasoning_buf += text
                        yield _step_event("thought", "delta", content=text)
                        if first_chunk:
                            first_chunk = False
            if getattr(delta, "tool_calls", None):
                for tc in delta.tool_calls or []:
                    idx = tc.index
                    while len(tool_calls) <= idx:
                        tool_calls.append({"id": "", "name": "", "arguments": ""})
                    if tc.id:
                        tool_calls[idx]["id"] = tc.id
                    if tc.function and tc.function.name:
                        tool_calls[idx]["name"] = tc.function.name
                    if tc.function and tc.function.arguments:
                        tool_calls[idx]["arguments"] += tc.function.arguments
            if choice.finish_reason:
                finish_reason = choice.finish_reason

        # ---- ReAct Step 1: 思考（end）----
        thought_summary = reasoning_buf.strip() or content_buf.strip()[:80] or "（模型未给出思考文本）"
        yield _step_event("thought", "end", summary=thought_summary)

        # ---- ReAct Step 2: 意图识别 ----
        yield _step_event("intent", "begin")
        intent_text = _intent_from_messages(messages, reasoning_buf)
        yield _step_event("intent", "delta", content=intent_text)
        yield _step_event("intent", "end", summary=intent_text)

        assistant_msg: Dict[str, Any] = {"role": "assistant"}
        if content_buf:
            assistant_msg["content"] = content_buf
        if reasoning_buf:
            assistant_msg["reasoning_content"] = reasoning_buf
        if tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                }
                for tc in tool_calls
            ]
        history.append(assistant_msg)

        # 没有工具调用 -> 结束
        if not tool_calls or finish_reason in ("stop", None):
            yield _step_event(
                "iterate",
                "begin",
            )
            yield _step_event(
                "iterate",
                "delta",
                content="无需工具调用，可直接基于已有信息回答用户。",
            )
            yield _step_event(
                "iterate",
                "end",
                summary="已得到完整答案。",
                decision="finish",
            )
            yield {"type": "done"}
            return

        # 执行每个工具（按 ReAct 步骤逐步 emit）
        for tc in tool_calls:
            name = tc["name"]
            args_str = tc["arguments"] or "{}"
            try:
                args = json.loads(args_str) if args_str else {}
            except json.JSONDecodeError:
                args = {}

            # ---- Step 3: 选择工具 ----
            # 外部 MCP 工具名形如 "{server_name}__{tool_name}"；先按 `__` 拆分出 server。
            tool_server: Optional[str] = None
            tool_label = name
            if "__" in name:
                tool_server = name.split("__", 1)[0]
                tool_label = f"{name}（来自 {tool_server} MCP）"

            yield _step_event("tool_select", "begin")
            yield _step_event("tool_select", "delta", content=f"决定调用 {tool_label}")
            yield _step_event("tool_select", "end", data={"name": name, "server": tool_server})

            # ---- Step 4: 构造参数 ----
            yield _step_event("args", "begin")
            args_preview = json.dumps(args, ensure_ascii=False)
            yield _step_event("args", "delta", content=args_preview)
            yield _step_event("args", "end", data={"args": args})

            # ---- Step 5: 执行调用 ----
            yield _step_event("action", "begin")
            action_text = f"调用 {tool_label}" if tool_server else f"调用 {name}（高德 MCP）"
            yield _step_event("action", "delta", content=action_text)
            if tool_server:
                # 外部 MCP 路由
                result = mcp_client.call_mcp_tool(name, args)
            else:
                if not amap_key:
                    result = {"error": "未配置高德 API Key，无法调用地图工具"}
                else:
                    result = amap_service.run_tool(name, args, amap_key)
            yield _step_event("action", "end", data={"name": name, "server": tool_server})

            payload = {"type": "tool", "name": name, "server": tool_server, "args": args, "result": result}
            yield payload
            if isinstance(tool_events, list):
                tool_events.append(payload)

            # ---- Step 6: 观察结果 ----
            yield _step_event("observation", "begin")
            obs_text = _summarize_tool_result(name, result)
            yield _step_event("observation", "delta", content=obs_text)
            yield _step_event("observation", "end", data={"name": name, "result": result}, summary=obs_text)

            history.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )

        # ---- Step 7: 迭代判断 ----
        yield _step_event("iterate", "begin")
        used_n = len(tool_calls)
        iter_text = f"本轮已调用 {used_n} 个工具，将结果回传模型继续推理。"
        yield _step_event("iterate", "delta", content=iter_text)
        yield _step_event("iterate", "end", summary=iter_text, decision="continue")

    yield _step_event("iterate", "begin")
    yield _step_event("iterate", "delta", content="已达到最大推理轮数（5），强制终止。")
    yield _step_event("iterate", "end", summary="工具调用过深，已自动终止。", decision="abort", status="error")
    yield {"type": "error", "message": "工具调用过深，已自动终止"}


# ---------------- 旅游计划 ----------------

TRAVEL_SYSTEM_PROMPT = """你是一名专业的中文旅行规划师。用户会给你出行需求（含偏好标签），你需要输出一份结构化、可以直接照着玩的 Markdown 行程表。

要求：
1. 输出合法的 Markdown，包含 1 个一级标题、若干"第N天"二级标题，每天内含：上午/中午/下午/晚上分段。
2. 每天至少给出一个 ⏰ 时间、📍 地点、🚗 交通方式、💡 简短理由；景点/餐饮要尽量具体到真实存在的地标。
3. 如果用户偏好中含"人文历史/美食体验/自然风光/现代都市/休闲度假/文艺体验"，务必在行程中体现。
4. 不要在正文里提示"以下是行程"等无用寒暄，直接给方案。
5. 自检：跨城行程需要标注起点到第一天的车程；天数整数天；人数体现在住宿/餐饮量上。
"""


def generate_travel_plan(payload: Dict[str, Any]) -> Dict[str, Any]:
    """兼容旧版同步调用：直接消费流式生成器的最终结果。"""
    final: Dict[str, Any] = {}
    for evt in generate_travel_plan_stream(payload):
        if evt.get("type") == "result":
            final = evt
    if final.get("ok"):
        return final
    return {"ok": False, "message": final.get("message") or "生成失败"}


def generate_travel_plan_stream(payload: Dict[str, Any]) -> Generator[Dict[str, Any], None, None]:
    """流式生成旅游 Markdown 计划，逐步 yield 进度事件。

    事件类型：
      - step (phase=begin|delta|end)：6 个阶段
      - delta：AI 阶段 markdown 内容流（兼容旧前端）
      - result：{ok, markdown, enrichments}
      - error / done
    """
    cfg = load_config()
    llm = cfg.get("llm") or {}

    try:
        cli = _client()
    except Exception as e:  # noqa: BLE001
        yield _travel_step("prepare", "begin")
        yield _travel_step("prepare", "end", summary=f"无法初始化客户端：{e}", status="error")
        yield {"type": "result", "ok": False, "message": f"无法初始化客户端：{e}"}
        yield {"type": "done"}
        return

    model = llm.get("model") or "MiniMax-M3"

    origin = (payload.get("origin") or "").strip()
    destination = (payload.get("destination") or "").strip()
    days = int(payload.get("days") or 1)
    people = payload.get("people") or 2
    prefs: List[str] = payload.get("preferences") or []
    extra = (payload.get("extra") or "").strip()
    use_map = bool(payload.get("use_map"))

    # ---- 1. 准备参数 ----
    yield _travel_step("prepare", "begin")
    yield _travel_step("prepare", "delta", content=f"出发地 {origin} → 目的地 {destination}，{days} 天 / {people} 人")
    yield _travel_step("prepare", "end", summary="出行参数已整理")

    user_msg_parts = [
        f"- 出发地：{origin or '（未填写）'}",
        f"- 目的地：{destination or '（未填写）'}",
        f"- 旅游天数：{days}",
        f"- 人数：{people}",
        f"- 偏好：{'、'.join(prefs) if prefs else '（未指定）'}",
    ]
    if extra:
        user_msg_parts.append(f"- 额外要求：{extra}")

    enrichments: List[str] = []
    amap_key = ((cfg.get("amap") or {}).get("api_key") or "").strip()

    o_loc: Optional[str] = None
    d_loc: Optional[str] = None
    d_city: Optional[str] = None

    if use_map and origin and destination and amap_key:
        # ---- 2. 地理编码 ----
        yield _travel_step("geocode", "begin")
        try:
            o = amap_service.geocode(origin, None, amap_key)
            d = amap_service.geocode(destination, None, amap_key)
            o_loc = o["location"]
            d_loc = d["location"]
            d_city = d.get("city") or destination
            yield _travel_step("geocode", "delta", content=f"出发地：{o['address']}")
            yield _travel_step("geocode", "delta", content=f"目的地：{d['address']}")
            yield _travel_step("geocode", "end",
                               summary=f"{o['address']} ↔ {d['address']}",
                               data={"origin": o, "destination": d})

            # ---- 3. 路径规划 ----
            yield _travel_step("route", "begin")
            try:
                route = amap_service.route_driving(o_loc, d_loc, amap_key)
                dist_km = route["distance"] / 1000.0
                dur_min = route["duration"] / 60.0
                enrichments.append(
                    f"参考：高德测算驾车约 {dist_km:.1f} km / {dur_min:.1f} 小时"
                )
                yield _travel_step("route", "delta", content=f"驾车约 {dist_km:.1f} km / {dur_min:.1f} 小时")
                yield _travel_step("route", "end",
                                   summary=f"约 {dist_km:.1f} km / {dur_min:.1f} 小时",
                                   data=route)
            except Exception as e:  # noqa: BLE001
                enrichments.append(f"路径规划失败：{e}")
                yield _travel_step("route", "end", summary=f"路径规划失败：{e}", status="error")

            # ---- 4. 天气 ----
            yield _travel_step("weather", "begin")
            try:
                w = amap_service.weather(d_city, amap_key)
                fc = (w.get("forecasts") or [{}])[0]
                if fc.get("casts"):
                    c = fc["casts"][0]
                    enrichments.append(
                        f"目的地 {d_city} 天气：白天 {c.get('dayweather')} {c.get('daytemp')}°C / 夜间 {c.get('nightweather')} {c.get('nighttemp')}°C"
                    )
                    yield _travel_step("weather", "delta",
                                       content=f"{d_city}：{c.get('dayweather')} {c.get('daytemp')}°C")
                    yield _travel_step("weather", "end",
                                       summary=f"{d_city} 天气已获取",
                                       data=w)
                else:
                    yield _travel_step("weather", "end", summary="天气数据为空")
            except Exception as e:  # noqa: BLE001
                yield _travel_step("weather", "end", summary=f"天气查询失败：{e}", status="error")
        except Exception as e:  # noqa: BLE001
            yield _travel_step("geocode", "end", summary=f"地理编码失败：{e}", status="error")
            enrichments.append(f"参考数据获取失败：{e}")
    elif use_map and not amap_key:
        yield _travel_step("geocode", "begin")
        yield _travel_step("geocode", "end", summary="未配置高德 API Key，跳过地图步骤", status="error")

    if enrichments:
        user_msg_parts.append("\n参考数据（直接采纳）：\n" + "\n".join(f"- {x}" for x in enrichments))

    user_msg = "\n".join(user_msg_parts) + "\n\n请输出 Markdown 行程表。"

    # ---- 5. AI 规划（流式）----
    yield _travel_step("ai", "begin")
    yield _travel_step("ai", "delta", content="AI 正在规划行程…")
    content = ""
    try:
        stream = cli.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": TRAVEL_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.7,
            stream=True,
            extra_body=_extra_body(llm),
        )
        for chunk in stream:
            try:
                choice = chunk.choices[0]
            except (IndexError, AttributeError):
                continue
            delta = choice.delta
            if getattr(delta, "content", None):
                content += delta.content
                yield {"type": "delta", "content": delta.content}
                yield _travel_step("ai", "delta", content=delta.content)
        yield _travel_step("ai", "end",
                           summary=f"AI 已生成 {len(content)} 字 Markdown",
                           data={"length": len(content)})
    except OpenAIError as e:
        yield _travel_step("ai", "end", summary=f"LLM 错误：{e}", status="error")
        yield {"type": "result", "ok": False, "message": f"LLM 错误：{e}"}
        yield {"type": "done"}
        return
    except Exception as e:  # noqa: BLE001
        yield _travel_step("ai", "end", summary=f"生成失败：{e}", status="error")
        yield {"type": "result", "ok": False, "message": f"生成失败：{e}"}
        yield {"type": "done"}
        return

    # ---- 6. 整合结果 ----
    yield _travel_step("integrate", "begin")
    yield _travel_step("integrate", "delta", content="整理 Markdown 与参考数据…")
    yield _travel_step("integrate", "end", summary="行程计划已就绪")

    yield {"type": "result", "ok": True, "markdown": content, "enrichments": enrichments}
    yield {"type": "done"}