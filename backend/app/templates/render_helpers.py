"""简历 → HTML 渲染助手。

逻辑逐字翻译自原 apps/api/src/resumes/templates/render-helpers.ts，行为保持一致。
所有函数只输出带 class 的纯标记（不含内联尺寸），间距/颜色由版式的 <style> 决定。
"""
from __future__ import annotations

import html
import re
from typing import Any, Optional


def escape_html(text: Any) -> str:
    s = str(text)
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def format_inline(text: Any) -> str:
    out = escape_html(str(text or ""))
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"__(.+?)__", r"<u>\1</u>", out)
    out = re.sub(r"\*(.+?)\*", r"<em>\1</em>", out)
    return out


def contact_emoji(kind: str) -> str:
    if kind == "email":
        return "📧"
    if kind == "phone":
        return "📱"
    return "📍"


def parse_markdown_list_line(line: str) -> dict:
    text = str(line or "").strip()
    unordered = re.match(r"^[-*+]\s*(.+)$", text)
    if unordered:
        return {"kind": "ul", "text": unordered.group(1)}
    ordered = re.match(r"^\d+[.)]\s*(.+)$", text)
    if ordered:
        return {"kind": "ol", "text": ordered.group(1)}
    return {"kind": "line", "text": text}


def render_detail_lines(lines: list[str], mode: str, detail_class: str | None = None) -> str:
    cleaned = [str(line).strip() for line in lines if str(line).strip()]
    if not cleaned:
        return ""

    if mode == "list":
        first = parse_markdown_list_line(cleaned[0])
        tag = "ol" if first["kind"] == "ol" else "ul"
        class_name = f' class="{detail_class}"' if detail_class else ""
        items = "".join(
            f"<li>{format_inline(parse_markdown_list_line(line)['text'])}</li>"
            for line in cleaned
        )
        return f"<{tag}{class_name}>{items}</{tag}>"

    detail_suffix = f" {detail_class}" if detail_class else ""
    parts: list[str] = []
    list_parts: list[tuple[str, list[str]]] = []

    def flush(active):  # type: ignore[no-untyped-def]
        if active is None:
            return
        kind, items = active
        body = "".join(f"<li>{format_inline(i)}</li>" for i in items)
        parts.append(f'<{kind} class="line-list{detail_suffix}">{body}</{kind}>')

    active = None  # type: ignore[assignment]
    for line in cleaned:
        parsed = parse_markdown_list_line(line)
        if parsed["kind"] in ("ul", "ol"):
            if active and active[0] != parsed["kind"]:
                flush(active)
                active = None
            if active is None:
                active = (parsed["kind"], [parsed["text"]])
            else:
                active[1].append(parsed["text"])
            continue
        flush(active)
        active = None
        parts.append(f'<div class="line-item">{format_inline(parsed["text"])}</div>')
    flush(active)

    return f'<div class="line-block{detail_suffix}">{"".join(parts)}</div>'


def section_block(title: str, rows: list[dict]) -> str:
    if not rows:
        return ""
    title_html = f"<h2>{title}</h2>" if str(title).strip() else ""
    content_class = "section-content" if str(title).strip() else "section-content no-title"
    content_html = ""
    for item in rows:
        head = item["head"] if item.get("headHtml") else f"<strong>{format_inline(item['head'])}</strong>"
        block_class = " ".join(x for x in ["block", item.get("blockClass")] if x)
        bullets = item.get("bullets") or []
        bullet_html = (
            render_detail_lines(bullets, item.get("bulletMode") or "list", item.get("detailClass"))
            if bullets
            else ""
        )
        sub = f'<div class="muted">{format_inline(item["sub"])}</div>' if item.get("sub") else ""
        content_html += (
            f'<div class="{block_class}"><div class="row"><div class="head">{head}</div>'
            f'<span class="time">{format_inline(item.get("time") or "")}</span></div>{sub}{bullet_html}</div>'
        )
    return f"{title_html}<div class=\"{content_class}\">{content_html}</div>"


def icon_from_label(label: str) -> str:
    if "求职" in label or "职业" in label:
        return "💼"
    if "意向" in label or "岗位" in label or "目标" in label:
        return "🎯"
    if "网站" in label or "链接" in label or "主页" in label:
        return "🔗"
    if "研究" in label or "方向" in label or "课题" in label:
        return "🔬"
    return "⭐"


def meta_item_html(icon: str, value: str) -> str:
    return (
        f'<span class="meta-item"><span class="meta-icon">{escape_html(icon)}</span>'
        f'<span class="meta-text">{escape_html(value)}</span></span>'
    )


def build_header_data(resume: dict) -> dict:
    basics = resume.get("basics") or {}
    header_meta_items = ""
    for icon, value in [
        (contact_emoji("email"), basics.get("email", "")),
        (contact_emoji("phone"), basics.get("phone", "")),
        (contact_emoji("location"), basics.get("location", "")),
    ]:
        if str(value or "").strip():
            header_meta_items += meta_item_html(icon, str(value))

    header_extra_entries = []
    for item in basics.get("extraInfos") or []:
        label = str(item.get("label", "")).strip()
        value = str(item.get("value", "")).strip()
        icon = str(item.get("icon", "")).strip()
        if label and value:
            header_extra_entries.append({"label": label, "value": value, "icon": icon})

    def extra_item_html(item: dict) -> str:
        icon = item["icon"] or icon_from_label(item["label"])
        return meta_item_html(icon, f"{item['label']}：{item['value']}")

    header_extra_items = "".join(extra_item_html(e) for e in header_extra_entries)
    centered_extra_rows = []
    for index, item in enumerate(header_extra_entries[:4]):
        row_index = index // 2
        if row_index >= len(centered_extra_rows):
            centered_extra_rows.append("")
        centered_extra_rows[row_index] += extra_item_html(item)

    photo = str(basics.get("photo") or "").strip()
    normalized_photo = (
        photo
        if photo.startswith("data:image/") or photo.startswith("https://") or photo.startswith("http://")
        else ""
    )
    header_photo = (
        f'<div class="avatar-wrap"><img class="avatar" src="{escape_html(normalized_photo)}" alt="profile photo" /></div>'
        if normalized_photo
        else ""
    )

    return {
        "headerMetaItems": header_meta_items,
        "headerExtraEntries": header_extra_entries,
        "headerExtraItems": header_extra_items,
        "centeredExtraRows": centered_extra_rows,
        "photoSrc": normalized_photo,
        "headerPhoto": header_photo,
    }


def plain_contact_lines(resume: dict) -> list[str]:
    basics = resume.get("basics") or {}
    contacts = " | ".join(
        str(x).strip() for x in [basics.get("email"), basics.get("phone"), basics.get("location")] if str(x or "").strip()
    )
    extras = " | ".join(
        f"{item.get('label')}: {item.get('value')}"
        for item in basics.get("extraInfos") or []
        if str(item.get("label") or "").strip() and str(item.get("value") or "").strip()
    )
    return [x for x in [contacts, extras] if x]


def build_education_block(resume: dict, title: str) -> str:
    rows = []
    for item in resume.get("education") or []:
        school = str(item.get("school") or "").strip()
        degree = str(item.get("degree") or "").strip()
        major = str(item.get("major") or "").strip()
        college = str(item.get("college") or "").strip()
        gpa = str(item.get("gpa") or "").strip()
        tags = str(item.get("schoolTags") or "").strip()
        start_date = str(item.get("startDate") or "").strip()
        end_date = str(item.get("endDate") or "").strip()

        # 学校标签合并进元信息行（胶囊样式），不再单独占一行
        tag_html = ""
        if tags:
            pills = "".join(
                f'<span class="edu-tag">{escape_html(t.strip())}</span>'
                for t in re.split(r"[,，/|、\s]+", tags)
                if t.strip()
            )
            tag_html = f'<span class="edu-tags">{pills}</span>'

        edu_meta = " ".join(x for x in [degree, major, college, f"GPA {gpa}" if gpa else ""] if x)
        left_parts = []
        if school:
            left_parts.append(f'<span class="edu-school">{escape_html(school)}</span>')
        if tag_html:
            left_parts.append(tag_html)
        if school and edu_meta:
            left_parts.append(" —— ")
        if edu_meta:
            left_parts.append(f'<span class="edu-meta">{escape_html(edu_meta)}</span>')
        left_text = "".join(left_parts)
        date_text = " - ".join(x for x in [start_date, end_date] if x)
        one_line = left_text or "教育经历"

        computed_bullets = []
        if isinstance(item.get("highlights"), list) and item["highlights"]:
            computed_bullets = [
                str(x)
                for x in item["highlights"]
                if not str(x).startswith(("GPA:", "所在学院:", "学校标签:"))
            ]
        else:
            computed_bullets = [
                f"简介: {item.get('summary')}" if item.get("summary") else "",
            ]
            computed_bullets = [x for x in computed_bullets if x]

        rows.append(
            {
                "head": one_line,
                "headHtml": True,
                "sub": "",
                "time": date_text,
                "bullets": computed_bullets,
                "blockClass": "edu-block",
                "detailClass": "edu-detail",
            }
        )
    return section_block(title, rows)


def build_custom_section_blocks(resume: dict) -> list[str]:
    out = []
    for section in resume.get("customSections") or []:
        sec_title = str(section.get("title") or "")
        is_work_like = bool(re.search(r"实习|工作", sec_title))
        is_project_like = bool(re.search(r"项目", sec_title))
        is_research_like = bool(re.search(r"科研|校园", sec_title))
        rows = []
        for item in section.get("items") or []:
            if is_work_like:
                company = str(item.get("org") or "").strip()
                role = str(item.get("title") or "").strip()
                head = ""
                if company:
                    head += f'<span class="exp-company">{escape_html(company)}</span>'
                if company and role:
                    head += " - "
                if role:
                    head += f'<span class="exp-role">{escape_html(role)}</span>'
                rows.append(
                    {
                        "head": head,
                        "headHtml": True,
                        "sub": "",
                        "time": item.get("period") or "",
                        "bullets": item.get("highlights") or [],
                        "bulletMode": "lines",
                        "blockClass": "compact-block",
                    }
                )
                continue
            if is_project_like:
                project_name = str(item.get("title") or "").strip()
                project_org = str(item.get("org") or "").strip()
                head = ""
                if project_name:
                    head += f'<span class="proj-name">{escape_html(project_name)}</span>'
                if project_name and project_org:
                    head += " - "
                if project_org:
                    head += f'<span class="proj-org">{escape_html(project_org)}</span>'
                rows.append(
                    {
                        "head": head,
                        "headHtml": True,
                        "sub": "",
                        "time": item.get("period") or "",
                        "bullets": item.get("highlights") or [],
                        "bulletMode": "lines",
                        "blockClass": "compact-block",
                    }
                )
                continue
            if is_research_like:
                title = str(item.get("title") or "").strip()
                org = str(item.get("org") or "").strip()
                rows.append(
                    {
                        "head": title or org,
                        "sub": org if title else "",
                        "time": item.get("period") or "",
                        "bullets": item.get("highlights") or [],
                        "bulletMode": "lines",
                        "blockClass": "compact-block",
                    }
                )
                continue
            title = str(item.get("title") or "").strip()
            org = str(item.get("org") or "").strip()
            rows.append(
                {
                    "head": title or org,
                    "sub": org if title else "",
                    "time": item.get("period") or "",
                    "bullets": item.get("highlights") or [],
                    "bulletMode": "lines",
                    "blockClass": "compact-block",
                }
            )
        out.append(section_block(sec_title, rows))
    return out


def build_legacy_blocks(resume: dict, titles: dict) -> str:
    exp_rows = []
    for item in resume.get("experience") or []:
        company = str(item.get("company") or "").strip()
        role = str(item.get("role") or "").strip()
        head = ""
        if company:
            head += f'<span class="exp-company">{escape_html(company)}</span>'
        if company and role:
            head += " - "
        if role:
            head += f'<span class="exp-role">{escape_html(role)}</span>'
        exp_rows.append(
            {
                "head": head,
                "headHtml": True,
                "sub": "",
                "time": f"{item.get('startDate')} - {item.get('endDate')}",
                "bullets": item.get("highlights") or [],
                "bulletMode": "lines",
                "blockClass": "compact-block",
            }
        )
    legacy_experience_block = section_block(titles["experience"], exp_rows)

    proj_rows = []
    for item in resume.get("projects") or []:
        project_name = str(item.get("name") or "").strip()
        project_org = str(item.get("description") or "").strip()
        head = ""
        if project_name:
            head += f'<span class="proj-name">{escape_html(project_name)}</span>'
        if project_name and project_org:
            head += " - "
        if project_org:
            head += f'<span class="proj-org">{escape_html(project_org)}</span>'
        proj_rows.append(
            {
                "head": head,
                "headHtml": True,
                "sub": "",
                "bullets": [str(x) for x in (item.get("highlights") or [])],
                "bulletMode": "lines",
                "blockClass": "compact-block",
            }
        )
    legacy_projects_block = section_block(titles["projects"], proj_rows)
    return f"{legacy_experience_block}{legacy_projects_block}"


def compute_spacing(body_font_size_pt: float, line_height: float) -> dict:
    block_gap_px = max(4, round(body_font_size_pt * max(0.45, min(0.75, line_height * 0.5))))
    section_title_top_px = max(4, round(body_font_size_pt * max(0.35, min(0.5, line_height * 0.33))))
    return {
        "blockGapPx": block_gap_px,
        "sectionTitleTopPx": section_title_top_px,
        "sectionTitleBottomPx": max(5, round(block_gap_px * 0.7)),
        "listTopPx": max(3, round(block_gap_px * 0.75)),
        "lineItemGapPx": max(1, round(block_gap_px * 0.35)),
        "listOuterIndentPx": max(10, round(body_font_size_pt * 1.2)),
        "listMarkerIndentPx": max(10, round(body_font_size_pt * 0.95)),
        "detailTopPx": max(1, round(block_gap_px * 0.25)),
        "detailLineItemGapPx": max(0, round(block_gap_px * 0.12)),
        "sectionContentIndentPx": max(14, round(body_font_size_pt * 1.6)),
        "compactBlockGapPx": max(2, round(block_gap_px * 0.45)),
        "educationBlockGapPx": max(2, round(block_gap_px * 0.45)),
        "educationListTopPx": max(2, round(block_gap_px * 0.35)),
        "educationLineItemGapPx": max(0, round(block_gap_px * 0.15)),
    }


def shared_list_css(s: dict) -> str:
    return (
        f"ul,ol{{margin:{s['listTopPx']}px 0 0 {s['listOuterIndentPx']}px;padding-left:{s['listMarkerIndentPx']}px}}"
        f"li{{margin:{s['lineItemGapPx']}px 0}}"
        f"ul.edu-detail,ol.edu-detail{{margin-top:{s['educationListTopPx']}px}}"
        f".edu-detail li{{margin:{s['educationLineItemGapPx']}px 0}}"
        f".line-block{{margin-top:{s['detailTopPx']}px}}"
        f".line-block.edu-detail{{margin-top:{s['educationListTopPx']}px}}"
        f".line-list{{margin:{s['detailLineItemGapPx']}px 0 0 {s['listOuterIndentPx']}px;padding-left:{s['listMarkerIndentPx']}px}}"
        f".line-list:first-child{{margin-top:0}}"
        f".line-list li{{margin:{s['detailLineItemGapPx']}px 0}}"
        f".line-item{{margin:{s['detailLineItemGapPx']}px 0}}"
        f".line-block .line-item:first-child{{margin-top:0}}"
        f".line-block .line-item:last-child{{margin-bottom:0}}"
        f".edu-detail .line-item{{margin:{s['educationLineItemGapPx']}px 0}}"
    )


def shared_block_css(s: dict) -> str:
    return (
        f".block{{margin-bottom:{s['blockGapPx']}px}}"
        f".compact-block{{margin-bottom:{s['compactBlockGapPx']}px}}"
        f".compact-block:last-child{{margin-bottom:0}}"
        f".edu-block{{margin-bottom:{s['educationBlockGapPx']}px}}"
        f".edu-block:last-child{{margin-bottom:0}}"
        f".row{{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}}"
        f".head{{min-width:0;flex:1 1 auto}}"
        f".time{{flex:0 0 auto;white-space:nowrap}}"
        f".edu-school{{font-weight:700}}"
        f".edu-meta{{font-weight:400}}"
        f".exp-company{{font-weight:700}}"
        f".exp-role{{font-weight:400}}"
        f".proj-name{{font-weight:700}}"
        f".proj-org{{font-weight:400}}"
        f".meta-item{{display:inline-flex;align-items:center;gap:5px}}"
        f".meta-icon{{width:14px;min-width:14px;display:inline-flex;align-items:center;justify-content:center;font-family:Apple Color Emoji,Segoe UI Emoji,Noto Color Emoji,sans-serif;font-size:11px}}"
    )
