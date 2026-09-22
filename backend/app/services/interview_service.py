"""AI 对话式模拟面试服务。

基于候选人简历 + 目标岗位/JD，进行逐题问答式面试：
面试官提问 → 候选人作答 → 面试官简要点评并提出下一问。
"""
from __future__ import annotations

from typing import Any

from ..llm.client import LlmClient, LlmContentError


def _build_resume_context(resume: dict) -> str:
    """把简历浓缩为面试官可见的文本上下文。"""
    parts: list[str] = []
    basics = resume.get("basics") or {}
    name = str(basics.get("name") or "").strip()
    summary = str(basics.get("summary") or "").strip()
    if name:
        parts.append(f"姓名：{name}")
    if summary:
        parts.append(f"个人简介：{summary}")

    edu_lines = []
    for e in resume.get("education") or []:
        school = str(e.get("school") or "").strip()
        degree = str(e.get("degree") or "").strip()
        major = str(e.get("major") or "").strip()
        period = " - ".join(
            x for x in [str(e.get("startDate") or "").strip(), str(e.get("endDate") or "").strip()] if x
        )
        line = " / ".join(x for x in [school, degree, major, period] if x)
        if line:
            edu_lines.append(line)
    if edu_lines:
        parts.append("教育经历：\n" + "\n".join("- " + x for x in edu_lines))

    sec_lines = []
    for s in resume.get("customSections") or []:
        title = str(s.get("title") or "").strip()
        items_txt = []
        for it in s.get("items") or []:
            t = str(it.get("title") or "").strip()
            org = str(it.get("org") or "").strip()
            period = str(it.get("period") or "").strip()
            head = " · ".join(x for x in [t, org, period] if x)
            hl = [str(x).strip() for x in (it.get("highlights") or []) if str(x).strip()]
            block = head
            if hl:
                block += "：" + "；".join(hl)
            if block:
                items_txt.append(block)
        if title and items_txt:
            sec_lines.append(f"【{title}】\n" + "\n".join("- " + x for x in items_txt))
    if sec_lines:
        parts.append("\n".join(sec_lines))

    skills = [str(x).strip() for x in (resume.get("skills") or []) if str(x).strip()]
    if skills:
        parts.append("技能：" + "、".join(skills))

    return "\n\n".join(parts) if parts else "（简历内容为空）"


async def interview_chat(
    *,
    resume: dict | None = None,
    resume_text: str | None = None,
    company: str,
    position: str,
    job_description: str,
    messages: list[dict],
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> dict:
    """进行一轮面试对话，返回面试官的回复。

    简历来源二选一：结构化 resume（档案）或 resume_text（PDF 导入的纯文本）。
    messages: 面试对话记录，候选人作答 role=user，面试官提问 role=assistant。
    """
    client = LlmClient(base_url=base_url, api_key=api_key, model=model)
    if not client.has_provider():
        raise LlmContentError(
            "缺少模型配置：请先在「设置」中填写大模型的 Base URL 与 API Key"
        )

    if resume_text and resume_text.strip():
        context = resume_text.strip()[:8000]
    elif resume:
        context = _build_resume_context(resume)
    else:
        raise LlmContentError("缺少简历：请选择档案或导入 PDF")
    system = f"""你是一位拥有多年一线经验的资深技术面试官，正在对候选人进行一场基于其简历的模拟面试。

【候选人简历】
{context}

【面试设定】
- 目标公司：{company or "未指定"}
- 目标岗位：{position or "未指定"}
- 岗位 JD：{job_description or "无"}

【你的行为规范】
1. 每次只提出一个问题，问题必须具体、贴合候选人简历中的项目与经历，绝不能空泛。
2. 当候选人回答后，先用 1-2 句简要点评其回答（指出亮点与不足），然后再提出下一个问题。
3. 问题应围绕简历项目层层追问：为什么这么做、具体如何实现、遇到什么困难、结果与数据如何、有无更优方案。
4. 语气专业、自然、克制，像真实面试官，用中文交流。
5. 只输出你对候选人说的话，不要输出任何解释、角色标签、Markdown 代码块或多余符号。
"""

    msgs: list[dict[str, Any]] = [{"role": "system", "content": system}]
    history = []
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "").strip()
        content = str(m.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            history.append({"role": role, "content": content})

    if not history:
        # 首次进入：触发开场白 + 第一个问题
        msgs.append(
            {
                "role": "user",
                "content": "请开始面试：先做一句简短的开场白，然后提出第一个问题。",
            }
        )
    else:
        msgs.extend(history)

    reply = await client.chat(msgs, temperature=0.7)
    return {"reply": reply.strip()}
