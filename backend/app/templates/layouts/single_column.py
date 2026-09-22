"""经典单栏版式渲染器。

逻辑逐字翻译自原 apps/api/src/resumes/templates/layouts/single-column.ts，
输出 HTML 与 PDF A4 预览保持一致。
"""
from __future__ import annotations

from typing import Any

from ..render_helpers import (
    build_custom_section_blocks,
    build_education_block,
    build_header_data,
    build_legacy_blocks,
    compute_spacing,
    escape_html,
    format_inline,
    shared_block_css,
    shared_list_css,
)


def render_single_column(resume: dict, template: dict, layout: dict | None = None) -> str:
    tokens = template.get("tokens") or {}
    layout = layout or {}

    page_margin = f"{layout.get('pageMarginMm') or float(str(tokens.get('pageMargin', '14mm')).replace('mm', ''))}mm"
    body_font_size_pt = float(layout.get("bodyFontSizePt") or float(str(tokens.get("bodyFontSize", "10.5pt")).replace("pt", "")))
    body_font_size = f"{body_font_size_pt:.1f}pt"
    line_height = layout.get("lineHeight") or tokens.get("lineHeight") or 1.5
    s = compute_spacing(body_font_size_pt, line_height)
    header_style = "centered" if layout.get("headerStyle") == "centered" else "default"
    header_bottom_gap_px = (
        max(2, round(s["blockGapPx"] * 0.45))
        if header_style == "centered"
        else max(3, round(s["blockGapPx"] * 0.6))
    )
    accent_color = layout.get("accentColor") or tokens.get("accentColor") or "#1f4f8f"
    font_family = layout.get("fontFamily") or tokens.get("fontFamily")
    text_color = tokens.get("textColor") or "#1f2937"
    font_size = body_font_size
    line_height_css = line_height

    section_titles = layout.get("sectionTitles") or {}
    titles = {
        "experience": section_titles.get("experience") or "Experience",
        "projects": section_titles.get("projects") or "Projects",
        "education": section_titles.get("education") or "教育经历",
        "skills": section_titles.get("skills") or "Skills",
    }

    legacy_rows = build_legacy_blocks(resume, {"experience": titles["experience"], "projects": titles["projects"]})
    custom_sections = "".join(build_custom_section_blocks(resume))
    legacy_education_block = build_education_block(resume, titles["education"])
    skills = " · ".join(resume.get("skills") or [])

    header_data = build_header_data(resume)
    header_meta_items = header_data["headerMetaItems"]
    header_extra_items = header_data["headerExtraItems"]
    centered_extra_rows = header_data["centeredExtraRows"]
    header_photo = header_data["headerPhoto"]

    centered_info_rows = ""
    rows = [header_meta_items] + centered_extra_rows
    for row in rows[:3]:
        if row:
            centered_info_rows += f'<div class="meta meta-line">{row}</div>'

    name_html = escape_html((resume.get("basics") or {}).get("name", ""))
    summary = (resume.get("basics") or {}).get("summary")

    model_extra = f'<div class="meta meta-extra">{header_extra_items}</div>' if header_extra_items else ""
    model_summary = f'<div class="summary">{format_inline(summary)}</div>' if summary else ""
    centered_photo_slot = header_photo or '<div class="header-slot"></div>'

    default_header = (
        '<div class="header"><div class="header-main"><div class="header-info">'
        + f"<h1>{name_html}</h1><div class=\"meta\">{header_meta_items}</div>"
        + model_extra
        + model_summary
        + f"</div>{header_photo}</div></div>"
    )
    centered_header = (
        '<div class="header header-centered"><div class="header-centered-layout"><div class="header-slot"></div>'
        + '<div class="header-centered-info">'
        + f"<h1>{name_html}</h1>{centered_info_rows}"
        + model_summary
        + f"</div>{centered_photo_slot}</div></div>"
    )
    header = centered_header if header_style == "centered" else default_header

    trailing_sections = custom_sections or legacy_rows
    body_sections = f"{legacy_education_block}{trailing_sections}"

    css = (
        "@page{size:A4;margin:"
        f"{page_margin}}}"
        f"body{{font-family:{font_family};color:{text_color};font-size:{font_size};line-height:{line_height_css}}}"
        f"h1{{margin:0;color:#111827;font-size:17pt;font-weight:700;letter-spacing:1.5px;"
        f"border-left:4px solid {accent_color};padding-left:10px;line-height:1.25}}"
        f"h2{{margin:{s['sectionTitleTopPx']}px 0 {s['sectionTitleBottomPx']}px;color:{accent_color};"
        f"font-size:12pt;font-weight:700;letter-spacing:1px;padding-bottom:3px;"
        f"border-bottom:2px solid transparent;"
        f"border-image:linear-gradient(90deg,{accent_color},rgba(0,0,0,0)) 1}}"
        f".header{{margin-bottom:{header_bottom_gap_px}px}}"
        ".header-main{display:flex;justify-content:space-between;align-items:flex-start;gap:14px}"
        ".header-info{min-width:0;flex:1 1 auto}"
        ".header-centered{text-align:center}"
        f".header-centered-layout{{display:grid;grid-template-columns:76px minmax(0,1fr) 76px;align-items:start;column-gap:10px}}"
        ".header-centered-info{min-width:0}"
        ".header-centered h1{line-height:1.15}"
        ".header-centered .meta{justify-content:center;flex-wrap:nowrap;column-gap:18px;row-gap:0;margin-top:3px}"
        ".header-centered .meta-text{white-space:nowrap}"
        ".header-centered .avatar-wrap{justify-self:end}"
        ".header-centered .avatar{width:60px;height:80px}"
        f".meta{{color:#4b5563;font-size:9.5pt;line-height:16px;margin-top:5px;display:flex;flex-wrap:wrap;align-items:center;column-gap:14px;row-gap:4px}}"
        ".meta-extra{margin-top:4px}"
        ".meta-item{display:inline-flex;align-items:center;height:16px;line-height:16px;gap:5px}"
        ".meta-text{display:inline-block;line-height:16px}"
        ".meta-icon{width:14px;min-width:14px;height:14px;display:inline-flex;align-items:center;justify-content:center;font-family:Apple Color Emoji,Segoe UI Emoji,Noto Color Emoji,sans-serif;font-size:11px;line-height:14px;vertical-align:middle}"
        ".avatar-wrap{flex:0 0 auto;border:1px solid #d1d5db;padding:2px;background:#fff;border-radius:3px}"
        ".avatar{width:78px;height:104px;object-fit:cover;display:block}"
        f".summary{{margin-top:8px;color:#374151;border-left:3px solid {accent_color}55;padding-left:9px}}"
        f".edu-tags{{display:inline-flex;gap:4px;margin-left:7px;vertical-align:1px}}"
        f".edu-tag{{font-size:8pt;font-weight:600;color:{accent_color};background:{accent_color}14;"
        f"border:1px solid {accent_color}38;border-radius:999px;padding:1px 7px;letter-spacing:.5px}}"
        f".section-content{{padding-left:{s['sectionContentIndentPx']}px}}"
        ".section-content.no-title{padding-left:0}"
        + shared_block_css(s)
        + ".muted{color:#4b5563}"
        + shared_list_css(s)
        + f".section-content{{color:#374151}}ul li::marker{{color:{accent_color}}}"
    )

    skills_html = (
        f'<h2>{titles["skills"]}</h2><div class="section-content">{format_inline(skills)}</div>'
        if skills
        else ""
    )

    return (
        '<!doctype html><html><head><meta charset="utf-8" />'
        f"<title>{name_html} - Resume</title><style>{css}</style></head>"
        f"<body>{header}{body_sections}{skills_html}</body></html>"
    )
