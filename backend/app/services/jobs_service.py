"""岗位分析服务：CSV 读取（mtime 缓存）+ 本地匹配算法 + 筛选排序。

纯本地实现，不调用 LLM。数据源为 backend/app/data/jobs.csv，
用户可用自己的 CSV 替换；读取逻辑对缺列/坏值保持容忍。
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any, Optional

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "jobs.csv"

# —— 模块级缓存：mtime 变化时重新加载 ——
_CACHE: dict[str, Any] = {"mtime": None, "jobs": []}


def _split_pipes(value: Any) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in str(value).split("|") if v.strip()]


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _row_to_job(row: dict, idx: int) -> dict:
    """把一行 CSV 转为标准岗位 dict，缺列/坏值容忍。"""
    get = lambda key, d="": (row.get(key) or "").strip() if isinstance(row.get(key), str) else row.get(key, d)  # noqa: E731
    salary_min = _to_int(row.get("salary_min"))
    salary_max = _to_int(row.get("salary_max"))
    return {
        "id": get("id") or f"ROW{idx}",
        "title": get("title") or "未命名岗位",
        "company": get("company") or "未知公司",
        "city": get("city") or "不限",
        "category": get("category") or "综合",
        "salaryMin": salary_min,
        "salaryMax": salary_max or salary_min,
        "experience": get("experience") or "不限",
        "education": get("education") or "不限",
        "skills": _split_pipes(row.get("skills")),
        "tags": _split_pipes(row.get("tags")),
        "benefits": _split_pipes(row.get("benefits")),
        "description": get("description"),
        "publishDate": get("publish_date") or get("publishDate") or "",
    }


def load_jobs() -> list[dict]:
    """读取岗位列表（带 mtime 失效缓存）。"""
    if not DATA_FILE.exists():
        return []
    mtime = DATA_FILE.stat().st_mtime
    if _CACHE["mtime"] == mtime and _CACHE["jobs"]:
        return _CACHE["jobs"]
    jobs: list[dict] = []
    try:
        with DATA_FILE.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if not any((v or "").strip() for v in row.values() if isinstance(v, str)):
                    continue  # 跳过空行
                jobs.append(_row_to_job(row, i + 1))
    except (OSError, csv.Error):
        jobs = []
    _CACHE["mtime"] = mtime
    _CACHE["jobs"] = jobs
    return jobs


def filter_jobs(
    jobs: list[dict],
    keyword: str = "",
    city: str = "",
    category: str = "",
) -> list[dict]:
    kw = (keyword or "").strip().lower()
    result = []
    for job in jobs:
        if city and job["city"] != city:
            continue
        if category and job["category"] != category:
            continue
        if kw:
            hay = "|".join(
                [job["title"], job["company"], job["category"], job["city"], job["description"]]
                + job["skills"] + job["tags"]
            ).lower()
            if kw not in hay:
                continue
        result.append(job)
    return result


def sort_jobs(jobs: list[dict], sort: str, score_map: Optional[dict] = None) -> list[dict]:
    """排序：salary（薪资上限降序）/ publish（发布日期降序）/ match（匹配分降序）。"""
    jobs = list(jobs)
    if sort == "salary":
        jobs.sort(key=lambda j: (j["salaryMax"], j["salaryMin"]), reverse=True)
    elif sort == "match" and score_map:
        jobs.sort(key=lambda j: score_map.get(j["id"], -1), reverse=True)
    else:
        jobs.sort(key=lambda j: j["publishDate"], reverse=True)
    return jobs


# ============================================================
# 本地匹配算法：技能 50% + 经验 30% + 学历 20%
# ============================================================

def _resume_full_text(resume: dict) -> str:
    """简历全文小写 dump，用于关键词子串命中。"""
    try:
        return json.dumps(resume, ensure_ascii=False).lower()
    except (TypeError, ValueError):
        return ""


def _walk_strings(value: Any):
    """递归遍历 dict/list，产出所有字符串（未转义，供中文正则匹配）。"""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _walk_strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _walk_strings(v)


def _resume_skill_tokens(resume: dict) -> list[str]:
    skills = resume.get("skills")
    if isinstance(skills, list):
        return [str(s).strip().lower() for s in skills if str(s).strip()]
    if isinstance(skills, str):
        return [s.strip().lower() for s in re.split(r"[|,，;；/]", skills) if s.strip()]
    return []


def _exp_lower_years(experience: str) -> Optional[int]:
    """解析岗位经验要求的年限下限；无法解析返回 None。"""
    exp = (experience or "").strip()
    if not exp or "不限" in exp:
        return 0
    m = re.search(r"(\d+(?:\.\d+)?)\s*[-~至到]\s*\d+", exp)
    if m:
        return int(float(m.group(1)))
    m = re.search(r"(\d+(?:\.\d+)?)\s*年", exp)
    if m:
        return int(float(m.group(1)))
    if "应届" in exp or "实习" in exp:
        return 0
    return None


def _estimate_years(resume: dict) -> Optional[int]:
    """从简历推断工作年数：全文「N年」线索取最大值。"""
    years: list[int] = []
    for s in _walk_strings(resume):
        years.extend(int(m) for m in re.findall(r"(\d+)\s*年", s))
    # 排除明显是日期/数量的噪音：只保留合理工作年限（0-40）
    years = [y for y in years if 0 <= y <= 40]
    return max(years) if years else None


def _work_entry_count(resume: dict) -> int:
    """统计 customSections 中工作类条目数量。"""
    count = 0
    work_keys = ("工作", "实习", "职业", "work", "experience", "employment")
    sections = resume.get("customSections")
    if isinstance(sections, list):
        for sec in sections:
            if not isinstance(sec, dict):
                continue
            title = str(sec.get("title") or "").lower()
            if any(k in title for k in work_keys):
                items = sec.get("items")
                count += len(items) if isinstance(items, list) else 1
    # 兼容 experience 数组字段
    exp = resume.get("experience")
    if isinstance(exp, list):
        count += len(exp)
    return count


_DEGREE_RANK = {"不限": 0, "大专": 1, "专科": 1, "本科": 2, "学士": 2, "硕士": 3, "研究生": 3, "博士": 4, "博士后": 4}


def _degree_rank(text: str) -> int:
    rank = 0
    for k, v in _DEGREE_RANK.items():
        if k in text:
            rank = max(rank, v)
    return rank


def match_resume(job: dict, resume: Optional[dict]) -> dict:
    if not resume or not isinstance(resume, dict):
        return {
            "score": 0, "skillsMatched": [], "skillsMissing": list(job.get("skills", [])),
            "expScore": 0, "eduScore": 0,
            "summary": "未提供简历，无法计算匹配度。",
        }

    # —— 1. 技能匹配（50%）——
    job_skills = job.get("skills") or []
    full_text = _resume_full_text(resume)
    skill_tokens = _resume_skill_tokens(resume)
    matched, missing = [], []
    for sk in job_skills:
        token = sk.strip().lower()
        if not token:
            continue
        hit = token in full_text or any(token in t or t in token for t in skill_tokens)
        (matched if hit else missing).append(sk)
    skill_ratio = (len(matched) / len(job_skills)) if job_skills else 1.0

    # —— 2. 经验匹配（30%）——
    lower = _exp_lower_years(job.get("experience", ""))
    years = _estimate_years(resume)
    entries = _work_entry_count(resume)
    if lower is None or lower <= 0:
        exp_score = 1.0
    elif years is None and entries <= 0:
        exp_score = 0.6  # 无法判断给 60%
    else:
        est = years if years is not None else float(entries)
        if est >= lower:
            exp_score = 1.0
        elif est >= lower - 1:
            exp_score = 0.8
        else:
            exp_score = max(0.2, round(est / max(lower, 1), 2) * 0.7)

    # —— 3. 学历匹配（20%）——
    job_edu = str(job.get("education") or "不限")
    job_rank = _degree_rank(job_edu) if job_edu != "不限" else 0
    edu_list = resume.get("education")
    resume_degrees = []
    if isinstance(edu_list, list):
        for e in edu_list:
            if isinstance(e, dict):
                resume_degrees.append(str(e.get("degree") or ""))
    resume_rank = max((_degree_rank(d) for d in resume_degrees), default=0)
    if "不限" in job_edu or job_rank <= 0:
        edu_score = 1.0
    elif resume_rank <= 0:
        edu_score = 0.7  # 无法判断给 70%
    elif resume_rank >= job_rank:
        edu_score = 1.0
    elif resume_rank == job_rank - 1:
        edu_score = 0.6
    else:
        edu_score = 0.3

    return _build_match(job_skills, matched, missing, exp_score, edu_score)


def match_resume_text(job: dict, text: str) -> dict:
    """基于纯文本简历（如 PDF 解析结果）的匹配算法，与结构化版同权重。"""
    t = str(text or "").lower()
    if not t.strip():
        return {
            "score": 0, "skillsMatched": [], "skillsMissing": list(job.get("skills", [])),
            "expScore": 0, "eduScore": 0,
            "summary": "未提供简历，无法计算匹配度。",
        }

    job_skills = job.get("skills") or []
    matched, missing = [], []
    for sk in job_skills:
        token = sk.strip().lower()
        if not token:
            continue
        (matched if token in t else missing).append(sk)
    skill_ratio = (len(matched) / len(job_skills)) if job_skills else 1.0

    # 经验：文本中「N年」线索
    lower = _exp_lower_years(job.get("experience", ""))
    years = [int(m) for m in re.findall(r"(\d+)\s*年", str(text or ""))]
    years = [y for y in years if 0 <= y <= 40]
    est = max(years) if years else None
    if lower is None or lower <= 0:
        exp_score = 1.0
    elif est is None:
        exp_score = 0.6
    elif est >= lower:
        exp_score = 1.0
    elif est >= lower - 1:
        exp_score = 0.8
    else:
        exp_score = max(0.2, round(est / max(lower, 1), 2) * 0.7)

    # 学历：文本关键词
    job_edu = str(job.get("education") or "不限")
    job_rank = _degree_rank(job_edu) if job_edu != "不限" else 0
    resume_rank = _degree_rank(str(text or "")[:4000])
    if "不限" in job_edu or job_rank <= 0:
        edu_score = 1.0
    elif resume_rank <= 0:
        edu_score = 0.7
    elif resume_rank >= job_rank:
        edu_score = 1.0
    elif resume_rank == job_rank - 1:
        edu_score = 0.6
    else:
        edu_score = 0.3

    return _build_match(job_skills, matched, missing, exp_score, edu_score)


def _build_match(job_skills: list, matched: list, missing: list, exp_score: float, edu_score: float) -> dict:
    """汇总加权得分与点评文案。"""
    skill_ratio = (len(matched) / len(job_skills)) if job_skills else 1.0
    total = round((skill_ratio * 0.5 + exp_score * 0.3 + edu_score * 0.2) * 100)
    total = max(0, min(100, total))

    if total >= 80:
        summary = f"高度匹配：核心技能命中 {len(matched)}/{len(job_skills)}，经验与学历均达标，建议优先投递。"
    elif total >= 60:
        gap = f"，可补充「{'、'.join(missing[:3])}」" if missing else ""
        summary = f"较为匹配：技能命中 {len(matched)}/{len(job_skills)}{gap}，整体竞争力不错。"
    elif total >= 40:
        summary = f"部分匹配：技能命中 {len(matched)}/{len(job_skills)}，存在明显缺口，建议针对性提升后再投递。"
    else:
        summary = f"匹配度偏低：仅命中 {len(matched)}/{len(job_skills)} 项技能，建议关注更贴合方向的岗位。"

    return {
        "score": total,
        "skillsMatched": matched,
        "skillsMissing": missing,
        "expScore": round(exp_score * 100),
        "eduScore": round(edu_score * 100),
        "summary": summary,
    }
