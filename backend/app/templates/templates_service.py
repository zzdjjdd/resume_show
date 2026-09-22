"""模板服务：模板列表与简历 HTML 渲染。

参考原 apps/api/src/resumes/templates.service.ts。
"""
from __future__ import annotations

from typing import Any, Optional

from ..schemas.resume_models import TemplateDefinition
from .layouts.single_column import render_single_column
from .layouts.modern_templates import (
    render_dual_column,
    render_minimal_ink,
    render_modern_pro,
)

MODERN_CN_TEMPLATE_ID = "modern-cn-001"

_TEMPLATES: list[dict] = [
    {
        "id": "modern-pro",
        "name": "现代专业",
        "description": "渐变顶栏 + 姓名强调线 + 时间胶囊，现代求职首选。",
        "layout": "single-column",
        "tokens": {"accentColor": "#4f46e5"},
    },
    {
        "id": "dual-column",
        "name": "双栏精英",
        "description": "深邃侧栏 + 菱形章节标记 + 发光技能点，高管气场。",
        "layout": "single-column",
        "tokens": {"accentColor": "#4f46e5"},
    },
    {
        "id": "minimal-ink",
        "name": "极简雅致",
        "description": "大字间距 + 章节编号 + 细线分隔，杂志级留白。",
        "layout": "single-column",
        "tokens": {"accentColor": "#111827"},
    },
    {
        "id": MODERN_CN_TEMPLATE_ID,
        "name": "Modern CN",
        "description": "中文单栏，左侧色块标题 + 渐变分隔，信息密度均衡。",
        "layout": "single-column",
        "tokens": {
            "fontFamily": "PingFang SC, Hiragino Sans GB, Microsoft YaHei, sans-serif",
            "accentColor": "#1f4f8f",
            "textColor": "#1f2937",
            "pageMargin": "14mm",
            "bodyFontSize": "10.5pt",
            "lineHeight": 1.5,
        },
    }
]

TEMPLATES = _TEMPLATES


class TemplatesService:
    def list(self) -> list[dict]:
        return _TEMPLATES

    def get_by_id(self, template_id: str) -> dict:
        for t in _TEMPLATES:
            if t["id"] == template_id:
                return t
        raise LookupError(f"Template {template_id} not found")

    def render_html(
        self, resume: dict, template_id: str = MODERN_CN_TEMPLATE_ID, layout: dict | None = None
    ) -> str:
        t = next(
            (item for item in _TEMPLATES if item["id"] == template_id),
            _TEMPLATES[0],
        )
        renderer = _RENDERERS.get(t["id"], render_single_column)
        return renderer(resume, t, layout)


_RENDERERS = {
    "modern-cn-001": render_single_column,
    "modern-pro": render_modern_pro,
    "minimal-ink": render_minimal_ink,
    "dual-column": render_dual_column,
}


templates_service = TemplatesService()
