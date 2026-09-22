"""AI 对话式一键生成简历服务。

支持两种交互：
- chat：AI 追问/引导，帮助用户补齐简历所需信息
- generate：基于对话内容一键生成结构化简历 JSON（符合 resume.schema.json）
"""
from __future__ import annotations

import json
from typing import Any

from ..llm.client import LlmClient, LlmContentError

SCHEMA_HINT = """
简历 JSON 结构（必须严格遵守，字段可缺省但不可新增）：
{
  "basics": {
    "name": "string，姓名",
    "email": "string，邮箱",
    "phone": "string，电话",
    "location": "string，城市",
    "summary": "string，2-3 句个人简介，突出方向与核心竞争力",
    "extraInfos": [{"label": "string", "value": "string", "icon": "string(emoji)"}]
  },
  "education": [
    {"school": "string", "degree": "string(本科/硕士/博士/大专)", "major": "string",
     "startDate": "YYYY-MM", "endDate": "YYYY-MM", "gpa": "string(可选)",
     "schoolTags": "string(可选,如985/211/双一流)", "highlights": ["string"]}
  ],
  "customSections": [
    {"title": "string(如 工作经历/项目经历/科研经历)",
     "items": [{"title": "string(职位或项目名)", "org": "string(公司/组织)",
                "period": "string(如 2022.07 ~ 至今)", "highlights": ["string，每条一个成果要点，尽量量化"]}]}
  ],
  "skills": ["string"]
}
"""

CHAT_SYSTEM = f"""你是资深简历顾问兼 HR 专家。你通过对话帮助用户准备一份专业、有竞争力的简历。

当前处于【对话收集】阶段，规则：
1. 判断用户已提供的信息是否足以生成一份完整简历（至少需要：基本身份 + 教育或工作/项目经历之一 + 技能方向）。
2. 若信息不足，友好地追问最关键的 1-3 项（姓名/联系方式/教育背景/工作与项目经历/技能），不要一次问太多，语气专业且亲切。
3. 若信息已足够，明确告诉用户「信息已足够，点击『一键生成简历』即可」，并可简要说明你将如何组织。
4. 回复用中文，简洁自然，不要输出 JSON，不要用 Markdown 代码块。
5. 绝不编造用户没有提到的事实。

参考的简历目标结构（仅供你判断信息是否完整）：
{SCHEMA_HINT}
"""

GEN_SYSTEM = f"""你是资深简历顾问。基于对话中用户提供的全部信息，生成一份专业、有竞争力、排版友好的简历。

【生成规则】
1. 只使用用户在对话中明确提供的信息；可润色措辞、突出成果与量化指标，但绝不编造不存在的经历、公司、数据。
2. 经历要点（highlights）用「动词开头 + 做了什么 + 方法/技术 + 量化结果」的句式，专业有力。
3. 个人简介（summary）2-3 句，突出职业方向与核心竞争力。
4. 若用户未提供邮箱，用 "your.email@example.com"；未提供电话用 "138-0000-0000"。
5. 时间统一为 YYYY-MM 或「YYYY.MM ~ 至今」格式。
6. customSections 按重要性排序（一般：工作/实习经历 > 项目经历 > 科研/校园经历）。
7. 只输出符合下述结构的 JSON，不要输出任何 Markdown、解释或代码块标记。
8. 【输出格式硬性要求】直接从字符 {{ 开始输出、以字符 }} 结束；
   严禁使用 ``` 或 ```json 代码块包裹；JSON 前后不得有任何文字、注释或空行；
   确保是合法 JSON（字符串用双引号、无尾逗号、控制字符需转义）。

{SCHEMA_HINT}
"""


def _normalize_generated_resume(raw: dict) -> dict:
    """清洗模型输出，确保符合 schema、可安全渲染。"""
    if not isinstance(raw, dict):
        raise LlmContentError("模型未返回有效的简历结构")

    basics_raw = raw.get("basics") or {}
    basics = {
        "name": str(basics_raw.get("name") or "未命名").strip() or "未命名",
        "email": str(basics_raw.get("email") or "your.email@example.com").strip(),
    }
    for key in ("phone", "location", "summary", "photo"):
        v = str(basics_raw.get(key) or "").strip()
        if v:
            basics[key] = v
    extras = []
    for item in basics_raw.get("extraInfos") or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        value = str(item.get("value") or "").strip()
        if label and value:
            row = {"label": label, "value": value}
            icon = str(item.get("icon") or "").strip()
            if icon:
                row["icon"] = icon
            extras.append(row)
    if extras:
        basics["extraInfos"] = extras

    out: dict[str, Any] = {"basics": basics}

    education = []
    for e in raw.get("education") or []:
        if not isinstance(e, dict):
            continue
        school = str(e.get("school") or "").strip()
        degree = str(e.get("degree") or "").strip()
        if not school:
            continue
        row = {
            "school": school,
            "degree": degree or "本科",
            "startDate": str(e.get("startDate") or "").strip(),
            "endDate": str(e.get("endDate") or "").strip(),
        }
        for key in ("major", "gpa", "schoolTags", "college", "summary"):
            v = str(e.get(key) or "").strip()
            if v:
                row[key] = v
        hl = [str(x).strip() for x in (e.get("highlights") or []) if str(x).strip()]
        if hl:
            row["highlights"] = hl
        education.append(row)
    if education:
        out["education"] = education

    custom_sections = []
    for s in raw.get("customSections") or []:
        if not isinstance(s, dict):
            continue
        title = str(s.get("title") or "").strip()
        items = []
        for it in s.get("items") or []:
            if not isinstance(it, dict):
                continue
            it_title = str(it.get("title") or "").strip()
            if not it_title:
                continue
            row = {"title": it_title}
            for key in ("org", "period"):
                v = str(it.get(key) or "").strip()
                if v:
                    row[key] = v
            hl = [str(x).strip() for x in (it.get("highlights") or []) if str(x).strip()]
            if hl:
                row["highlights"] = hl
            items.append(row)
        if title and items:
            custom_sections.append({"title": title, "items": items})
    if custom_sections:
        out["customSections"] = custom_sections

    skills = [str(x).strip() for x in (raw.get("skills") or []) if str(x).strip()]
    if skills:
        out["skills"] = skills

    return out


async def ai_chat_step(
    *,
    messages: list[dict],
    want_generate: bool = False,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> dict:
    """对话式生成简历。

    want_generate=False：返回 {type:"chat", reply}，AI 继续追问/引导。
    want_generate=True：返回 {type:"resume", resume, reply}，一键生成简历 JSON。
    """
    client = LlmClient(base_url=base_url, api_key=api_key, model=model)
    if not client.has_provider():
        raise LlmContentError(
            "缺少模型配置：请在服务端配置 INTERVIEW_API_KEY / INTERVIEW_BASE_URL（或 OPENAI_API_KEY）"
        )

    # 规整历史消息
    history = []
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "").strip()
        content = str(m.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            history.append({"role": role, "content": content})
    if not history:
        raise LlmContentError("请先输入你的背景信息")

    if not want_generate:
        prompt_msgs = [{"role": "system", "content": CHAT_SYSTEM}, *history]
        reply = await client.chat(prompt_msgs, temperature=0.6)
        return {"type": "chat", "reply": reply.strip() or "请继续补充你的信息。"}

    # 一键生成
    transcript = "\n".join(
        f"{'用户' if m['role'] == 'user' else '顾问'}：{m['content']}" for m in history
    )
    prompt_msgs = [
        {"role": "system", "content": GEN_SYSTEM},
        {
            "role": "user",
            "content": f"以下是与用户的完整对话记录，请据此生成简历 JSON：\n\n{transcript}\n\n"
            "现在请直接输出简历 JSON（从 { 开始，不要用代码块包裹，不要输出任何其他文字）。",
        },
    ]
    parsed = await client.chat_json(prompt_msgs, temperature=0.4)
    resume = _normalize_generated_resume(parsed)
    return {
        "type": "resume",
        "resume": resume,
        "reply": "已根据你的信息生成简历，可在右侧预览，或保存到简历档案继续编辑。",
    }
