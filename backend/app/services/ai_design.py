"""AI 简历排版设计服务。

不使用固定模板：让大模型基于用户简历 JSON，直接用 HTML + CSS
设计出【两版】风格不同、精美、可打印（A4）的完整简历文档，
用户可二选一，不满意可重新生成。

两版采用【双路并行】生成（每路只输出一版），显著降低单次输出长度，
避免超长 JSON 被截断导致解析失败；单路失败时保留另一路结果。
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from ..llm.client import LlmClient, LlmContentError

DESIGN_SYSTEM = """你是一位顶级的简历视觉设计师兼前端工程师。
根据给定的简历 JSON，设计并输出一版精美、可直接打印的完整 HTML 简历。

【硬性要求】
1. 只输出一个 JSON 对象，结构如下：
{"name":"版式名称(4-8个字)","desc":"一句话风格说明(20字内)","html":"完整HTML文档字符串"}
2. html 是完整的独立 HTML 文档（以 <!DOCTYPE html> 开头），所有样式写在 <style> 标签内；
   禁止引用任何外部资源（无外链字体 / 图片 / JS / CSS）。
3. 页面按 A4（210mm 宽）排版，正文容器宽 210mm、内边距 14-18mm；
   CSS 中必须包含 @page { size: A4; margin: 0; }，body 无外边距；
   正文字号 12-14px，行高 1.5-1.7，内容尽量一页呈现（信息多时允许自然换页）。
4. 必须完整呈现简历 JSON 中的全部信息（基本信息、个人简介、教育经历、各经历模块、技能），
   不得遗漏，更不得编造 JSON 里没有的内容。
5. 设计要精美——讲究对齐、留白、信息层级，可用细分隔线、色块、标签胶囊、时间轴等细节点缀。
6. 姓名必须最突出；联系方式一行排布；经历要点用精致的项目符号；技能可用胶囊标签。
7. 【输出格式硬性要求】直接从字符 { 开始输出、以字符 } 结束；
   严禁使用 ``` 或 ```json 代码块包裹；JSON 前后不得有任何文字、注释或空行；
   html 字段必须是合法 JSON 字符串（内部双引号、换行等控制字符全部正确转义）；
   不得有尾逗号。若内容较长，宁可精简要点也不要截断 JSON。
只输出 JSON，不要输出任何解释、注释或 Markdown 标记。"""

DIRECTIONS = [
    {
        "hint": (
            "【本版风格方向 A】现代商务双栏：左侧深色侧边栏（联系方式/技能/附加信息），"
            "右侧主区突出经历；配色沉稳（深蓝/墨青 + 一个亮色点缀），专业高管气场。"
        ),
        "fallback_name": "方案A · 现代双栏",
    },
    {
        "hint": (
            "【本版风格方向 B】极简高级单栏：大量留白、精致字体层级、细分隔线与灰阶文字，"
            "只用一个克制的强调色（如墨绿/藏青/绛紫），杂志排版质感。"
        ),
        "fallback_name": "方案B · 极简单栏",
    },
]


def _clean_html(html: str) -> str:
    """去掉模型可能包裹的 ```html 代码块标记。"""
    s = str(html or "").strip()
    if s.startswith("```"):
        lines = s.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    return s


def _normalize_single(parsed: Any, fallback_name: str) -> dict | None:
    """把单路结果规整为 {name, desc, html}；不可用返回 None。"""
    # 兼容模型仍返回 {"versions": [...]} 包裹的情况
    if isinstance(parsed, dict) and isinstance(parsed.get("versions"), list) and parsed["versions"]:
        parsed = parsed["versions"][0]
    if not isinstance(parsed, dict):
        return None
    html = _clean_html(parsed.get("html") or "")
    if "<" not in html or ">" not in html:
        return None
    if not html.lstrip().lower().startswith("<!doctype"):
        html = "<!DOCTYPE html>\n" + html
    name = str(parsed.get("name") or "").strip() or fallback_name
    desc = str(parsed.get("desc") or "").strip()
    return {"name": name, "desc": desc, "html": html}


async def _design_one(
    resume: dict,
    direction: dict,
    *,
    base_url: str | None,
    api_key: str | None,
    model: str | None,
) -> dict | None:
    """生成单版排版；失败返回 None（由上层保留其他路的结果）。"""
    client = LlmClient(base_url=base_url, api_key=api_key, model=model, timeout_ms=240000)
    prompt_msgs = [
        {"role": "system", "content": DESIGN_SYSTEM},
        {
            "role": "user",
            "content": direction["hint"] + "\n\n以下是简历 JSON：\n\n"
            + json.dumps(resume, ensure_ascii=False, indent=2)
            + "\n\n现在请直接输出符合要求的 JSON（从 { 开始，不要用代码块包裹，不要输出任何其他文字）。",
        },
    ]
    try:
        parsed = await client.chat_json(prompt_msgs, temperature=0.9, timeout_ms=240000)
        return _normalize_single(parsed, direction["fallback_name"])
    except LlmContentError:
        return None


async def design_resume(
    *,
    resume: dict,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    direction: int | None = None,
) -> dict:
    """基于简历 JSON 生成 AI 自定义排版。

    direction 为 None 时并行生成两版；指定 0/1 时只生成对应一版
    （前端用于「先出一版快速预览，另一版后台补充」的提速策略）。

    返回 {versions: [{name, desc, html}]}
    """
    if not isinstance(resume, dict) or not resume:
        raise LlmContentError("缺少简历数据，请先生成简历")

    probe = LlmClient(base_url=base_url, api_key=api_key, model=model)
    if not probe.has_provider():
        raise LlmContentError("缺少模型配置：请先在「大模型设置」中配置 Base URL 与 API Key")

    if direction is not None:
        dirs = [DIRECTIONS[int(direction) % len(DIRECTIONS)]]
    else:
        dirs = DIRECTIONS

    results = await asyncio.gather(
        *[
            _design_one(resume, d, base_url=base_url, api_key=api_key, model=model)
            for d in dirs
        ]
    )
    versions = [v for v in results if v]
    if not versions:
        raise LlmContentError("排版设计失败：模型未返回可用结果，请重试或更换模型")
    return {"versions": versions}
