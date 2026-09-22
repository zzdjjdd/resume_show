"""简历 LLM 能力：AI 润色 + 简单模拟面试 + JD 匹配项目上下文提取。

逻辑翻译自原 apps/api/src/resumes/resumes.controller.ts 的
polishResumeContent / simulateInterview / extractProjectContext。
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from ..config import resolve_interview_base_url, resolve_interview_model
from ..llm.client import LlmClient, LlmContentError


def extract_project_context(resume: dict) -> list[dict]:
    """从 projects 与自定义「项目」模块聚合项目上下文。"""
    out: list[dict] = []

    for item in resume.get("projects") or []:
        if not isinstance(item, dict):
            continue
        highlights = [
            str(x).strip()
            for x in (item.get("highlights") or [])
            if isinstance(x, str) and str(x).strip()
        ]
        row = {
            "name": str(item.get("name") or "").strip(),
            "org": str(item.get("org") or "").strip(),
            "description": str(item.get("description") or "").strip(),
            "highlights": highlights,
        }
        out.append(row)

    for section in resume.get("customSections") or []:
        if not isinstance(section, dict):
            continue
        if not re.search(r"项目|project", str(section.get("title") or ""), re.IGNORECASE):
            continue
        for item in section.get("items") or []:
            if not isinstance(item, dict):
                continue
            highlights = [
                str(x).strip()
                for x in (item.get("highlights") or [])
                if isinstance(x, str) and str(x).strip()
            ]
            row = {
                "name": str(item.get("title") or "").strip(),
                "org": str(item.get("org") or "").strip(),
                "period": str(item.get("period") or "").strip(),
                "highlights": highlights,
            }
            if row.get("name") or row.get("org") or highlights:
                out.append(row)

    return [r for r in out if any(r.values())]


def _normalize_ai_required(client: LlmClient) -> None:
    if not client.has_provider():
        raise LlmContentError(
            "缺少模型配置：请在服务端配置 INTERVIEW_BASE_URL / INTERVIEW_API_KEY（或 DASHSCOPE_API_KEY / OPENAI_*）"
        )


async def polish_resume_items(
    *,
    targets: list[dict],
    resume: dict,
    job_description: str,
    target_position: str,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> dict:
    """对选中的简历条目做最小改动强化润色，返回 normalized items。"""
    if not targets:
        raise LlmContentError("请至少选择一个需要润色的条目")
    if len(targets) > 20:
        raise LlmContentError("一次最多润色 20 个条目")

    client = LlmClient(base_url=base_url, api_key=api_key, model=model)
    _normalize_ai_required(client)

    jd = str(job_description or "").strip()
    position = str(target_position or "").strip() or "目标岗位"
    project_context = extract_project_context(resume)

    system_prompt = "你是资深技术简历顾问。你只返回 JSON，不返回 Markdown 和额外解释。"
    user_prompt = f"""
你需要根据岗位 JD，对候选人选中的简历条目进行“最小改动的强化润色”。

【规则】
1. 只润色用户选中的条目，不要扩展到未选中条目。
2. 不得编造候选人没有提供的经历、结果、指标。
3. 允许重写表达顺序、语句精炼、突出技术决策和业务价值。
4. 如果原文缺少量化数据，只能给“建议补充项”，不能凭空写具体数字。
5. 保留原有语义，修改幅度克制，突出与 JD 的匹配度。
6. 每个条目都给出：
   - polishedTitle/polishedOrg/polishedPeriod/polishedBullets
   - jdRelevance: high|medium|low|none（与岗位 JD 的相关性）
   - jdImprovements: 仅当 jdRelevance 为 high/medium/low 时给 1-3 条“下一步优化建议”；如果 jdRelevance=none 必须为空数组
   - changeSummary: 简述你改了什么、为什么
7. “下一步优化建议”必须具体到可执行动作，禁止空泛话术（如“继续优化”、“加强学习”）。
8. 若条目与 JD 明显无关（如方向不匹配的科研条目），只做表达润色，jdRelevance=none，且 jdImprovements=[]。

【岗位信息】
- 目标岗位：{position}
- 岗位 JD：{jd or "无"}

【候选人简历上下文（仅辅助理解，不可改写未选中内容）】
{json.dumps(project_context, ensure_ascii=False, indent=2)}

【待润色条目】
{json.dumps(targets, ensure_ascii=False, indent=2)}

【输出格式】
只输出 JSON：
{{
  "items": [
    {{
      "id": "string，对应输入 id",
      "polishedTitle": "string",
      "polishedOrg": "string",
      "polishedPeriod": "string",
      "polishedBullets": "string，多行文本，用\\n分隔",
      "jdRelevance": "high|medium|low|none",
      "jdImprovements": ["string"],
      "changeSummary": "string"
    }}
  ]
}}
"""

    parsed = await client.chat_json(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.4,
    )

    raw_items = parsed.get("items") if isinstance(parsed.get("items"), list) else []
    normalized = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "").strip()
        if not item_id:
            continue
        improvements = [
            str(x).strip()
            for x in (item.get("jdImprovements") or [])
            if isinstance(x, str) and str(x).strip()
        ]
        relevance = str(item.get("jdRelevance") or "").strip() or "medium"
        normalized.append(
            {
                "id": item_id,
                "polishedTitle": str(item.get("polishedTitle") or "").strip(),
                "polishedOrg": str(item.get("polishedOrg") or "").strip(),
                "polishedPeriod": str(item.get("polishedPeriod") or "").strip(),
                "polishedBullets": str(item.get("polishedBullets") or "").strip(),
                "jdRelevance": relevance,
                "jdImprovements": improvements if relevance != "none" else [],
                "changeSummary": str(item.get("changeSummary") or "").strip(),
            }
        )
    return {"items": normalized}


async def simulate_interview(
    *,
    resume: dict,
    company_name: str,
    target_position: str,
    job_description: str,
    language: str = "zh",
    rounds: int = 6,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> dict:
    """基于 JD 与项目经历生成模拟面试题。"""
    client = LlmClient(base_url=base_url, api_key=api_key, model=model)
    _normalize_ai_required(client)

    rounds = max(3, min(12, int(rounds or 6)))
    company = str(company_name or "").strip()
    role = str(target_position or "").strip() or "技术岗位"
    jd = str(job_description or "").strip()
    lang = "en" if str(language) == "en" else "zh"
    project_context = extract_project_context(resume)
    if not project_context:
        raise LlmContentError("当前简历缺少项目经历，无法生成项目面试问题")

    system_prompt = (
        "You are a ByteDance P8 interviewer. Return strict JSON only."
        if lang == "en"
        else "你是字节跳动 P8 技术面试官。只返回 JSON，不要返回其他文本。"
    )
    user_prompt = f"""
你是一名具有多年一线工程经验的技术面试官，正在面试「{company or "目标公司"}」的「{role}」候选人。

你的任务不是泛泛生成面试题，而是基于【岗位 JD】和【候选人项目经历】进行真实技术面试追问。
你需要像真实面试官一样，关注候选人的项目是否真实、技术选择是否合理、工程实现是否落地、是否有数据支撑，以及是否能解释关键取舍。

【候选人项目经历】
以下内容只包含项目经历，不包含个人隐私信息：
{json.dumps(project_context, ensure_ascii=False, indent=2)}

【岗位 JD】
{jd or "无"}

【面试目标】
请围绕岗位要求和候选人项目，生成 {rounds} 个高质量面试问题。

【出题原则】
1. 必须优先围绕 JD 中最相关的能力点提问，而不是平均覆盖所有项目。
2. 项目/业务相关问题占 80%，八股/基础问题占 20%。
3. 每个项目问题都必须从候选人简历中的具体表述出发，不能泛泛问概念。
4. 重点追问：为什么这么做、具体怎么实现、和其他方案相比为什么选这个、遇到了什么工程问题、效果如何验证、有没有数据指标支撑、如果线上部署延迟/成本/稳定性怎么处理、如果数据量扩大 10 倍方案是否还能成立。
5. 如果项目描述缺少量化结果、线上部署、评估指标、消融实验、异常处理、性能优化等信息，要主动生成追问。
6. 如果候选人使用了常见技术方案（RAG、Agent、LangGraph、向量检索、Cross-Encoder、LoRA、DPO、Tool Use、微调、蒸馏、缓存、异步并发、队列、数据库、Embedding、重排序等），需要追问其真实工程细节。
7. 问题要体现真实面试官的怀疑感和工程判断力，避免过于友好、宽泛、模板化。
8. 不要只问“你介绍一下项目”，而要问具体矛盾、具体取舍、具体指标。
9. 不要编造候选人没有提供的项目结果。如果项目缺少结果，要把它作为风险点追问。
10. 每个问题都要给出“面试官希望听到的点”，用于后续评分。

【问题类型要求】
- 项目真实性追问 / 技术选型追问 / 工程落地追问 / 性能效率追问 / 评估指标追问 / 失败案例追问 / 业务理解追问 / 基础八股追问（只问与项目强相关）

【输出约束】
1. questions 数组长度必须严格等于 {rounds}。
2. 如果 sourceProject 无法匹配，必须写空字符串，不得编造项目名。
3. expectedAnswer 尽量不超过 120 字，suggestedPreparation 尽量不超过 80 字。
4. 只输出 JSON，不要输出 Markdown，不要输出解释性文字。

JSON 格式如下：
{{
  "opening": "string，面试开场白，简短自然",
  "interviewRole": "string，面试岗位",
  "jdFocus": ["string，岗位最关注的能力点"],
  "projectRiskSummary": [
    {{"projectName": "string", "risk": "string", "reason": "string"}}
  ],
  "questions": [
    {{
      "category": "project|fundamental",
      "difficulty": "easy|medium|hard",
      "sourceProject": "string，问题来自哪个项目；基础题可为空",
      "resumeEvidence": "string，问题基于简历中的哪句话或哪个技术点",
      "question": "string，主问题",
      "whyAsk": "string，面试官为什么会问这个问题",
      "focus": "string，本题考察重点",
      "followUp": "string，候选人回答较浅时的继续追问",
      "expectedAnswer": "string，较好的回答应该包含什么",
      "expectedPoints": ["string"],
      "redFlags": ["string"],
      "suggestedPreparation": "string"
    }}
  ],
  "scoreCriteria": ["string"],
  "tips": ["string"]
}}
"""

    content = await client.chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
    )
    parsed = client.try_parse_json(content)
    if parsed:
        return _normalize_interview_payload(parsed, role, lang)

    # 兜底：模型返回非 JSON
    return {
        "opening": "Mock interview started." if lang == "en" else "模拟面试已开始。",
        "interviewRole": role,
        "questions": [
            {
                "question": content,
                "focus": "Model raw output fallback" if lang == "en" else "模型原始输出兜底",
                "followUp": "",
                "expectedAnswer": (
                    "Explain context, solution, trade-off and measurable impact."
                    if lang == "en"
                    else "说明业务背景、方案设计、关键取舍与量化结果。"
                ),
                "expectedPoints": [],
            }
        ],
        "scoreCriteria": [],
        "tips": [],
    }


def _normalize_interview_payload(payload: dict, fallback_role: str, lang: str) -> dict:
    raw_questions = payload.get("questions") if isinstance(payload.get("questions"), list) else []
    questions = []
    for item in raw_questions:
        if isinstance(item, str):
            questions.append(
                {
                    "category": "project",
                    "question": item,
                    "focus": "",
                    "followUp": "",
                    "expectedAnswer": "",
                    "expectedPoints": [],
                }
            )
            continue
        if not isinstance(item, dict):
            continue
        question_text = str(item.get("question") or "").strip()
        if not question_text:
            continue
        questions.append(
            {
                "category": str(item.get("category") or "project"),
                "question": question_text,
                "focus": str(item.get("focus") or "").strip(),
                "followUp": str(item.get("followUp") or "").strip(),
                "expectedAnswer": str(item.get("expectedAnswer") or "").strip(),
                "expectedPoints": [
                    str(x).strip()
                    for x in (item.get("expectedPoints") or [])
                    if isinstance(x, str) and str(x).strip()
                ],
            }
        )

    return {
        "opening": str(payload.get("opening") or "模拟面试已开始。"),
        "interviewRole": str(payload.get("interviewRole") or "").strip() or fallback_role or "技术岗位",
        "questions": questions,
        "scoreCriteria": [
            str(x).strip()
            for x in (payload.get("scoreCriteria") or [])
            if isinstance(x, str) and str(x).strip()
        ],
        "tips": [
            str(x).strip()
            for x in (payload.get("tips") or [])
            if isinstance(x, str) and str(x).strip()
        ],
    }
