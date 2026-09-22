"""岗位分析路由：岗位列表查询 + 简历匹配度计算。"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from ..services import jobs_service

router = APIRouter(tags=["jobs"])


def list_jobs_api(
    keyword: str = "",
    city: str = "",
    category: str = "",
    sort: str = "",
    limit: Optional[int] = None,
):
    """岗位列表：支持关键词/城市/类别筛选与排序。"""
    all_jobs = jobs_service.load_jobs()
    jobs = jobs_service.filter_jobs(all_jobs, keyword=keyword, city=city, category=category)
    jobs = jobs_service.sort_jobs(jobs, sort=(sort or "publish").lower())
    if limit and limit > 0:
        jobs = jobs[:limit]
    cities = sorted({j["city"] for j in all_jobs if j["city"]})
    categories = sorted({j["category"] for j in all_jobs if j["category"]})
    return {"jobs": jobs, "total": len(jobs), "cities": cities, "categories": categories}


@router.post("/jobs/match")
def match_jobs(
    resume: Any = Body(default=None),
    resume_text: Optional[str] = Body(default=None, alias="resumeText"),
    job_id: Optional[str] = Body(default=None, alias="jobId"),
):
    """简历匹配：支持结构化 resume 或纯文本 resumeText（PDF 导入）。

    传 jobId 返回单个 {job, match}；否则返回全部 {matches:[{jobId, score}]}。
    """
    all_jobs = jobs_service.load_jobs()
    text = str(resume_text or "").strip()
    has_text = bool(text)
    empty_resume = not resume or not isinstance(resume, dict) or not any(resume.values())

    def do_match(job: dict) -> dict:
        if has_text:
            return jobs_service.match_resume_text(job, text)
        if empty_resume:
            return {"score": 0, "skillsMatched": [], "skillsMissing": job["skills"],
                    "expScore": 0, "eduScore": 0, "summary": "未提供有效简历，所有匹配度记为 0。"}
        return jobs_service.match_resume(job, resume)

    if job_id:
        job = next((j for j in all_jobs if j["id"] == job_id), None)
        if job is None:
            return JSONResponse(status_code=404, content={"detail": f"岗位 {job_id} 不存在"})
        return {"job": job, "match": do_match(job)}

    matches = [{"jobId": job["id"], "score": do_match(job)["score"]} for job in all_jobs]
    resp: dict[str, Any] = {"matches": matches}
    if empty_resume and not has_text:
        resp["note"] = "未提供有效简历，所有匹配度记为 0；请选择简历档案或上传简历 PDF。"
    return resp
