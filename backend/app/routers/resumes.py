"""简历模块 API 路由。

路径与原 apps/api/src/resumes/resumes.controller.ts 保持一致。
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Response
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from ..config import resolve_interview_api_key, resolve_interview_base_url, resolve_interview_model
from ..llm.client import LlmContentError
from ..services import resume_llm
from ..services.pdf_export import PdfExportError, render_pdf, render_pdf_from_html
from ..services.resumes_service import BadRequest, NotFound, ResumeError, ResumeService
from ..templates.templates_service import templates_service

router = APIRouter()

# 全局单例服务（进程内内存存储）
resume_service = ResumeService()


def _error_response(exc: ResumeError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


# ---- Backward-compatible legacy routes ----
@router.post("/resumes")
def create_resume(body: Any = Body(...)):
    try:
        return resume_service.create(body)
    except ResumeError as exc:
        return _error_response(exc)


@router.get("/resumes")
def find_all_resumes():
    return resume_service.find_all()


@router.get("/resumes/{file_id}")
def find_one_resume(file_id: str):
    try:
        return resume_service.find_one(file_id)
    except ResumeError as exc:
        return _error_response(exc)


# ---- New multi-file routes ----
@router.get("/resume-files")
def list_resume_files():
    return resume_service.list_files()


@router.get("/resume-files/default")
def get_default_resume_file():
    try:
        return resume_service.get_default_file()
    except ResumeError as exc:
        return _error_response(exc)


@router.get("/resume-files/{file_id}")
def get_resume_file(file_id: str):
    try:
        return resume_service.get_file(file_id)
    except ResumeError as exc:
        return _error_response(exc)


@router.post("/resume-files")
def create_resume_file(
    name: Optional[str] = Body(default=None),
    resume: Any = Body(default=None),
    config: Optional[dict] = Body(default=None),
):
    try:
        return resume_service.create_file(name=name, resume=resume, file_config=config)
    except ResumeError as exc:
        return _error_response(exc)


@router.put("/resume-files/{file_id}")
def update_resume_file(file_id: str, resume: Any = Body(...), config: Optional[dict] = Body(default=None)):
    try:
        return resume_service.update_file(file_id, resume, config)
    except ResumeError as exc:
        return _error_response(exc)


@router.patch("/resume-files/{file_id}")
def rename_resume_file(file_id: str, name: str = Body(...)):
    try:
        return resume_service.rename_file(file_id, name)
    except ResumeError as exc:
        return _error_response(exc)


@router.patch("/resume-files/{file_id}/default")
def set_default_resume_file(file_id: str):
    try:
        return resume_service.set_default_file(file_id)
    except ResumeError as exc:
        return _error_response(exc)


@router.delete("/resume-files/{file_id}")
def delete_resume_file(file_id: str):
    try:
        return resume_service.delete_file(file_id)
    except ResumeError as exc:
        return _error_response(exc)


# ---- Templates & Export ----
@router.get("/templates")
def list_templates():
    return templates_service.list()


@router.post("/export/html", response_class=HTMLResponse)
def export_html(resume: Any = Body(...), template_id: Optional[str] = Body(default=None, alias="templateId"), layout: Optional[dict] = Body(default=None)):
    try:
        valid = resume_service.ensure_valid_resume(resume)
    except ResumeError as exc:
        return _error_response(exc)
    return templates_service.render_html(valid, template_id or "modern-cn-001", layout)


@router.post("/export/pdf")
async def export_pdf(
    resume: Any = Body(...),
    template_id: Optional[str] = Body(default=None, alias="templateId"),
    layout: Optional[dict] = Body(default=None),
):
    try:
        valid = resume_service.ensure_valid_resume(resume)
        pdf = await render_pdf(valid, template_id or "modern-cn-001", layout)
    except ResumeError as exc:
        return _error_response(exc)
    except PdfExportError as exc:
        return JSONResponse(status_code=503, content={"detail": str(exc)})
    headers = {"Content-Disposition": "attachment; filename=\"resume-preview.pdf\""}
    return Response(content=pdf, media_type="application/pdf", headers=headers)


@router.post("/export/pdf-html")
async def export_pdf_html(body: dict = Body(...)):
    """把完整 HTML 文档（如 AI 自定义排版）直接导出为 A4 PDF。

    body: { html: string }
    """
    html = str(body.get("html") or "").strip()
    if not html or not html.startswith("<"):
        return JSONResponse(status_code=400, content={"detail": "HTML 内容为空或非法"})
    try:
        pdf = await render_pdf_from_html(html)
    except PdfExportError as exc:
        return JSONResponse(status_code=503, content={"detail": str(exc)})
    headers = {"Content-Disposition": "attachment; filename=\"resume-ai-design.pdf\""}
    return Response(content=pdf, media_type="application/pdf", headers=headers)


# ---- AI polish & simple interview ----
@router.post("/interview/simulate")
async def simulate_interview(body: dict = Body(...)):
    try:
        resume = body.get("resume")
        if resume is None:
            resume_file_id = body.get("resumeFileId")
            if resume_file_id:
                resume = resume_service.get_file(resume_file_id)["data"]
            else:
                resume = resume_service.get_default_file()["data"]
        valid = resume_service.ensure_valid_resume(resume)
        result = await resume_llm.simulate_interview(
            resume=valid,
            company_name=body.get("companyName") or "",
            target_position=body.get("targetPosition") or body.get("interviewRole") or "",
            job_description=body.get("jobDescription") or "",
            language=body.get("language") or "zh",
            rounds=int(body.get("rounds") or 6),
            base_url=body.get("baseUrl"),
            api_key=body.get("apiKey"),
            model=body.get("model"),
        )
        return result
    except (ResumeError, LlmContentError) as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})


@router.post("/resume/polish")
async def polish_resume(body: dict = Body(...)):
    try:
        resume = body.get("resume")
        if resume is None:
            resume_file_id = body.get("resumeFileId")
            if resume_file_id:
                resume = resume_service.get_file(resume_file_id)["data"]
            else:
                resume = resume_service.get_default_file()["data"]
        valid = resume_service.ensure_valid_resume(resume)
        result = await resume_llm.polish_resume_items(
            targets=body.get("targets") or [],
            resume=valid,
            job_description=body.get("jobDescription") or "",
            target_position=body.get("targetPosition") or "",
            base_url=body.get("baseUrl"),
            api_key=body.get("apiKey"),
            model=body.get("model"),
        )
        return result
    except (ResumeError, LlmContentError) as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})
