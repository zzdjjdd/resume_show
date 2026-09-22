"""AI 路由：对话式生成简历 + 对话式模拟面试 + PDF 简历导入。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, File, Form, UploadFile
from fastapi.responses import JSONResponse

from ..llm.client import LlmContentError
from ..services import ai_design, ai_generate, interview_service
from ..services.pdf_parse import PdfParseError, parse_resume_pdf
from .resumes import resume_service

router = APIRouter()


@router.post("/resume/ai-chat")
async def ai_chat(body: dict[str, Any] = Body(...)):
    """对话式生成简历。

    body: { messages: [{role, content}], wantGenerate?: bool }
    返回：
      - wantGenerate=false → {type:"chat", reply}
      - wantGenerate=true  → {type:"resume", resume, reply}
    """
    try:
        return await ai_generate.ai_chat_step(
            messages=body.get("messages") or [],
            want_generate=bool(body.get("wantGenerate") or False),
            base_url=body.get("baseUrl"),
            api_key=body.get("apiKey"),
            model=body.get("model"),
        )
    except LlmContentError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=502, content={"detail": f"AI 服务异常：{exc}"})


@router.post("/resume/ai-design")
async def ai_resume_design(body: dict[str, Any] = Body(...)):
    """AI 自定义排版：不用固定模板，直接生成精美 HTML 简历。

    body: { resume: dict, baseUrl?, apiKey?, model?, direction?(0|1) }
    不传 direction 时并行生成两版；传 direction 只生成对应一版（提速）。
    返回：{ versions: [{name, desc, html}] }
    """
    try:
        return await ai_design.design_resume(
            resume=body.get("resume") or {},
            base_url=body.get("baseUrl"),
            api_key=body.get("apiKey"),
            model=body.get("model"),
            direction=body.get("direction"),
        )
    except LlmContentError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=502, content={"detail": f"AI 服务异常：{exc}"})


@router.post("/interview/parse-pdf")
async def interview_parse_pdf(
    file: UploadFile = File(...),
    base_url: str | None = Form(default=None, alias="baseUrl"),
    api_key: str | None = Form(default=None, alias="apiKey"),
    model: str | None = Form(default=None),
):
    """解析简历 PDF：优先抽取文本层，扫描件自动降级为多模态模型 OCR。

    multipart/form-data：file=<pdf>，可选 baseUrl/apiKey/model（供 OCR 使用）。
    返回：{ text, pages, method: "text"|"ocr", truncated }
    """
    filename = (file.filename or "").lower()
    if not filename.endswith(".pdf"):
        return JSONResponse(status_code=400, content={"detail": "请上传 PDF 文件"})
    try:
        data = await file.read()
        result = await parse_resume_pdf(
            data, base_url=base_url, api_key=api_key, model=model
        )
        return result
    except PdfParseError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=502, content={"detail": f"PDF 解析异常：{exc}"})


@router.post("/interview/ai-chat")
async def interview_chat(body: dict[str, Any] = Body(...)):
    """基于简历的对话式模拟面试。

    body: { resumeFileId?|resume?|resumeText?, company, position, jobDescription,
            messages: [{role, content}], baseUrl?, apiKey?, model? }
    返回：{ reply }（面试官的提问/点评）
    """
    try:
        resume_text = str(body.get("resumeText") or "").strip()
        resume = body.get("resume")
        if resume is None and not resume_text:
            fid = body.get("resumeFileId")
            if fid:
                resume = resume_service.get_file(fid)["data"]
            else:
                resume = resume_service.get_default_file()["data"]
        if resume is not None:
            resume = resume_service.ensure_valid_resume(resume)
        return await interview_service.interview_chat(
            resume=resume,
            resume_text=resume_text or None,
            company=body.get("company") or "",
            position=body.get("position") or "",
            job_description=body.get("jobDescription") or "",
            messages=body.get("messages") or [],
            base_url=body.get("baseUrl"),
            api_key=body.get("apiKey"),
            model=body.get("model"),
        )
    except LlmContentError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=502, content={"detail": f"AI 服务异常：{exc}"})
