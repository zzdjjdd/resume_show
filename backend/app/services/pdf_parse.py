"""简历 PDF 解析服务。

两级策略：
1. 首选：PyMuPDF 直接抽取文本层（绝大多数文字型 PDF）。
2. 兜底：文本层为空（扫描件）时，把页面渲染成 PNG，
   调用用户配置的 OpenAI 兼容多模态模型做 OCR 识别。
"""
from __future__ import annotations

import base64
from typing import Any

from ..llm.client import LlmClient, LlmContentError

MIN_TEXT_LEN = 80        # 文本少于此长度视为扫描件
MAX_OCR_PAGES = 4        # OCR 最多处理页数（控制 token 成本）
RENDER_DPI = 150         # OCR 渲染分辨率
MAX_TEXT_CHARS = 12000   # 返回文本上限


class PdfParseError(RuntimeError):
    pass


def _extract_text(data: bytes) -> tuple[str, int]:
    """返回 (文本, 页数)。"""
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:  # pragma: no cover
        raise PdfParseError("服务端缺少 PyMuPDF，请先执行 pip install pymupdf") from exc

    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:  # noqa: BLE001
        raise PdfParseError(f"PDF 打开失败：{exc}") from exc

    pages = len(doc)
    if pages == 0:
        raise PdfParseError("PDF 没有任何页面")
    texts = []
    for page in doc:
        texts.append(page.get_text("text"))
    doc.close()
    return "\n".join(texts).strip(), pages


def _render_pages_png(data: bytes, max_pages: int) -> list[str]:
    """把前 N 页渲染为 base64 PNG，供多模态模型 OCR。"""
    import fitz

    doc = fitz.open(stream=data, filetype="pdf")
    images: list[str] = []
    zoom = RENDER_DPI / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    for i, page in enumerate(doc):
        if i >= max_pages:
            break
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        images.append(base64.b64encode(pix.tobytes("png")).decode("ascii"))
    doc.close()
    return images


async def _ocr_with_llm(
    images_b64: list[str],
    *,
    base_url: str | None,
    api_key: str | None,
    model: str | None,
) -> str:
    """调用配置的多模态模型识别页面图片为文本。"""
    client = LlmClient(base_url=base_url, api_key=api_key, model=model, timeout_ms=180000)
    if not client.has_provider():
        raise PdfParseError(
            "该 PDF 没有可抽取的文本层（疑似扫描件），"
            "请先在「大模型设置」中配置支持图片识别的模型以启用 OCR"
        )

    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                "以下是一份简历 PDF 的页面截图。请完整、逐字地把其中的文字识别并输出为纯文本，"
                "保持原有段落与换行结构，不要总结、不要翻译、不要添加任何解释或标记。"
            ),
        }
    ]
    for img in images_b64:
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{img}"},
            }
        )

    msgs = [
        {"role": "system", "content": "你是一名专业的文档 OCR 引擎，只输出识别出的原文文本。"},
        {"role": "user", "content": content},
    ]
    try:
        reply = await client.chat(msgs, temperature=0.1)
    except LlmContentError as exc:
        raise PdfParseError(f"OCR 识别失败：{exc}") from exc
    return reply.strip()


async def parse_resume_pdf(
    data: bytes,
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> dict:
    """解析简历 PDF，返回 {text, pages, method}。

    method: "text"（直接抽取）或 "ocr"（模型识别）。
    """
    if not data:
        raise PdfParseError("上传内容为空")
    if len(data) > 20 * 1024 * 1024:
        raise PdfParseError("PDF 过大（>20MB），请压缩后再上传")

    text, pages = _extract_text(data)
    method = "text"

    if len(text.strip()) < MIN_TEXT_LEN:
        images = _render_pages_png(data, MAX_OCR_PAGES)
        if not images:
            raise PdfParseError("PDF 页面渲染失败，无法识别")
        text = await _ocr_with_llm(
            images, base_url=base_url, api_key=api_key, model=model
        )
        method = "ocr"

    text = text.strip()
    if not text:
        raise PdfParseError("未能从 PDF 中识别出任何文字")

    return {
        "text": text[:MAX_TEXT_CHARS],
        "pages": pages,
        "method": method,
        "truncated": len(text) > MAX_TEXT_CHARS,
    }
