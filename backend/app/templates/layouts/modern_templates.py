# -*- coding: utf-8 -*-
"""三套高端简历模板渲染器（modern-pro / minimal-ink / dual-column）。

每套模板输出完整 HTML（内联 <style>），与实时预览 / PDF 导出共用同一渲染结果。
字体栈统一为跨平台可用的优质中文字体，确保预览与 PDF 渲染一致。
"""
from __future__ import annotations

import re
from typing import Any

from ..render_helpers import escape_html, format_inline, parse_markdown_list_line

# 统一的优质中文字体栈：优先思源/苹方，回退微软雅黑，保证跨平台一致且观感高端
FONT_SANS = (
    "'Source Han Sans SC','Noto Sans SC','PingFang SC','Hiragino Sans GB',"
    "'Microsoft YaHei','微软雅黑',sans-serif"
)
FONT_SERIF = (
    "'Source Han Serif SC','Noto Serif SC','Songti SC','SimSun','宋体',serif"
)


# ---------------------------------------------------------------- 数据准备
def _contact_items(basics: dict) -> list[tuple[str, str]]:
    rows = [
        ("📧", basics.get("email") or ""),
        ("📱", basics.get("phone") or ""),
        ("📍", basics.get("location") or ""),
    ]
    return [(i, str(v).strip()) for i, v in rows if str(v).strip()]


def _extra_items(basics: dict) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for item in basics.get("extraInfos") or []:
        label = str(item.get("label") or "").strip()
        value = str(item.get("value") or "").strip()
        icon = str(item.get("icon") or "").strip() or "⭐"
        if label and value:
            out.append((icon, f"{label}：{value}"))
    return out


def _photo_src(basics: dict) -> str:
    photo = str(basics.get("photo") or "").strip()
    if photo.startswith("data:image/") or photo.startswith("http://") or photo.startswith("https://"):
        return photo
    return ""


def _bullet_html(lines: list[str]) -> str:
    """要点列表：支持 markdown 行内格式与 - / 1. 列表标记。"""
    items: list[str] = []
    for raw in lines:
        line = str(raw).strip()
        if not line:
            continue
        parsed = parse_markdown_list_line(line)
        items.append(f"<li>{format_inline(parsed['text'])}</li>")
    if not items:
        return ""
    return f'<ul class="bullets">{"".join(items)}</ul>'


def _edu_rows(resume: dict) -> list[dict]:
    rows = []
    for e in resume.get("education") or []:
        school = str(e.get("school") or "").strip()
        degree = str(e.get("degree") or "").strip()
        major = str(e.get("major") or "").strip()
        college = str(e.get("college") or "").strip()
        gpa = str(e.get("gpa") or "").strip()
        tags = str(e.get("schoolTags") or "").strip()
        start = str(e.get("startDate") or "").strip()
        end = str(e.get("endDate") or "").strip()
        meta = " · ".join(x for x in [degree, major, college, f"GPA {gpa}" if gpa else ""] if x)
        # 学校标签以胶囊形式跟在学校名后，不单独占一行
        tags_html = ""
        if tags:
            pills = "".join(
                f'<span class="edu-tag">{escape_html(t.strip())}</span>'
                for t in re.split(r"[,，/|、\s]+", tags)
                if t.strip()
            )
            tags_html = f'<span class="edu-tags">{pills}</span>'
        hl = [str(x) for x in (e.get("highlights") or []) if str(x).strip()]
        hl = [x for x in hl if not x.startswith(("学校标签:", "GPA:", "所在学院:"))]
        hl = [x[3:].strip() if x.startswith("简介:") else x for x in hl]
        summary = str(e.get("summary") or "").strip()
        if summary and summary not in hl:
            hl = [summary] + hl
        rows.append({"school": school, "meta": meta, "tags_html": tags_html, "time": " - ".join(x for x in [start, end] if x), "bullets": hl})
    return rows


def _section_rows(resume: dict) -> list[dict]:
    """合并 customSections（优先）与 legacy experience/projects。"""
    sections: list[dict] = []
    for s in resume.get("customSections") or []:
        items = []
        for it in s.get("items") or []:
            items.append({
                "title": str(it.get("title") or "").strip(),
                "org": str(it.get("org") or "").strip(),
                "period": str(it.get("period") or "").strip(),
                "bullets": [str(x) for x in (it.get("highlights") or []) if str(x).strip()],
            })
        if items:
            sections.append({"title": str(s.get("title") or "").strip(), "items": items})
    if not sections:
        legacy: list[dict] = []
        exp_items = [{
            "title": str(x.get("role") or "").strip(),
            "org": str(x.get("company") or "").strip(),
            "period": " - ".join(y for y in [str(x.get("startDate") or ""), str(x.get("endDate") or "")] if y.strip()),
            "bullets": [str(h) for h in (x.get("highlights") or []) if str(h).strip()],
        } for x in resume.get("experience") or []]
        if exp_items:
            legacy.append({"title": "工作经历", "items": exp_items})
        proj_items = [{
            "title": str(x.get("name") or "").strip(),
            "org": "",
            "period": "",
            "bullets": [str(h) for h in (x.get("highlights") or []) if str(h).strip()],
        } for x in resume.get("projects") or []]
        if proj_items:
            legacy.append({"title": "项目经历", "items": proj_items})
        sections = legacy
    return sections


def _layout_common(template: dict, layout: dict | None) -> dict:
    layout = layout or {}
    tokens = template.get("tokens") or {}
    # 用户选择的字体优先；否则用统一的高端无衬线栈（保证预览/PDF 一致）
    font_family = layout.get("fontFamily") or FONT_SANS
    return {
        "accent": layout.get("accentColor") or tokens.get("accentColor") or "#4f46e5",
        "margin": f"{layout.get('pageMarginMm') or 14}mm",
        "font_size": f"{layout.get('bodyFontSizePt') or 10.5}pt",
        "line_height": layout.get("lineHeight") or 1.5,
        "font_family": font_family,
    }


def _page_wrap(title: str, css: str, body: str, margin: str, font_family: str, font_size: str, line_height: float) -> str:
    return (
        '<!doctype html><html><head><meta charset="utf-8" />'
        f"<title>{title}</title><style>"
        f"@page{{size:A4;margin:{margin}}}"
        f"*{{box-sizing:border-box}}"
        f"html,body{{margin:0;padding:0}}"
        f"body{{font-family:{font_family};font-size:{font_size};line-height:{line_height};"
        f"color:#1f2430;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}}"
        f"h1,h2,h3,p,ul,li{{font-family:inherit}}"
        f"{css}</style></head><body>{body}</body></html>"
    )


def _entry_block(item: dict, period_right: bool = True) -> str:
    title = escape_html(item["title"] or item["org"] or "未命名条目")
    org = f'<span class="org">{escape_html(item["org"])}</span>' if item["org"] and item["title"] else ""
    period = f'<span class="period">{escape_html(item["period"])}</span>' if item.get("period") and period_right else ""
    return (
        f'<div class="entry"><div class="entry-head"><span class="entry-title">{title}</span>{org}{period}</div>'
        f"{_bullet_html(item['bullets'])}</div>"
    )


# ---------------------------------------------------------------- 模板 1：现代专业
def render_modern_pro(resume: dict, template: dict, layout: dict | None = None) -> str:
    c = _layout_common(template, layout)
    accent = c["accent"]
    basics = resume.get("basics") or {}
    name = escape_html(basics.get("name") or "")
    summary = str(basics.get("summary") or "").strip()
    contacts = _contact_items(basics)
    extras = _extra_items(basics)
    photo = _photo_src(basics)
    skills = [str(x).strip() for x in (resume.get("skills") or []) if str(x).strip()]

    contact_html = "".join(
        f'<span class="c-item"><span class="c-ic">{ic}</span>{escape_html(v)}</span>' for ic, v in contacts
    )
    extra_html = "".join(
        f'<span class="x-tag"><span class="c-ic">{ic}</span>{escape_html(v)}</span>' for ic, v in extras
    )
    photo_html = f'<img class="avatar" src="{escape_html(photo)}" alt="" />' if photo else ""
    summary_html = f'<div class="summary">{format_inline(summary)}</div>' if summary else ""

    body_sections = []
    edu = _edu_rows(resume)
    if edu:
        rows = "".join(
            f'<div class="entry"><div class="entry-head"><span class="entry-title">{escape_html(e["school"])}</span>'
            f'{e["tags_html"]}'
            f'<span class="period">{escape_html(e["time"])}</span></div>'
            + (f'<div class="edu-meta">{escape_html(e["meta"])}</div>' if e["meta"] else "")
            + _bullet_html(e["bullets"])
            + "</div>"
            for e in edu
        )
        body_sections.append(f'<section><h2>教育经历</h2>{rows}</section>')
    for sec in _section_rows(resume):
        rows = "".join(_entry_block(it) for it in sec["items"])
        body_sections.append(f"<section><h2>{escape_html(sec['title'])}</h2>{rows}</section>")
    if skills:
        tags = "".join(f"<span class='skill-tag'>{escape_html(s)}</span>" for s in skills)
        body_sections.append(f"<section><h2>技能</h2><div class='skills'>{tags}</div></section>")

    css = f"""
.topbar{{height:6px;background:linear-gradient(90deg,{accent} 0%,#a855f7 55%,#ec4899 100%);
margin:-{c['margin']} -{c['margin']} 18px}}
header{{display:flex;justify-content:space-between;align-items:flex-start;gap:18px}}
.head-main{{flex:1;min-width:0}}
h1{{margin:0 0 8px;font-size:27pt;font-weight:800;color:#0f172a;letter-spacing:1.2px;line-height:1.12}}
.name-accent{{width:58px;height:4px;border-radius:2px;margin:0 0 11px;
background:linear-gradient(90deg,{accent},#a855f7)}}
.contact{{display:flex;flex-wrap:wrap;align-items:center;gap:6px 16px;font-size:9.5pt;color:#475569}}
.c-item{{display:inline-flex;align-items:center;gap:5px;white-space:nowrap}}
.c-ic{{font-size:9.5pt;opacity:.9}}
.x-row{{margin-top:9px;display:flex;flex-wrap:wrap;gap:6px}}
.x-tag{{display:inline-flex;align-items:center;gap:5px;font-size:8.8pt;color:{accent};
background:{accent}0f;border:1px solid {accent}30;border-radius:999px;padding:3px 11px}}
.avatar{{width:88px;height:116px;object-fit:cover;border-radius:10px;border:1px solid #e2e8f0;
box-shadow:0 3px 12px rgba(15,23,42,.12)}}
.summary{{margin-top:13px;background:linear-gradient(90deg,{accent}0d,{accent}04);
border-left:3px solid {accent};border-radius:0 9px 9px 0;padding:9px 14px;color:#334155;font-size:9.8pt;line-height:1.65}}
section{{margin-top:16px}}
h2{{display:flex;align-items:center;gap:9px;margin:0 0 10px;font-size:12pt;font-weight:800;
color:#0f172a;letter-spacing:1.2px}}
h2::before{{content:"";width:4px;height:16px;border-radius:2px;
background:linear-gradient(180deg,{accent},#a855f7)}}
h2::after{{content:"";flex:1;height:1px;background:linear-gradient(90deg,#e2e8f0,transparent)}}
.entry{{margin-bottom:10px}}
.entry-head{{display:flex;align-items:baseline;gap:9px}}
.entry-title{{font-weight:700;color:#0f172a;font-size:1.02em}}
.org{{color:#64748b;font-size:9.5pt}}
.period{{margin-left:auto;color:#64748b;font-size:8.6pt;white-space:nowrap;
font-variant-numeric:tabular-nums;background:#f1f5f9;border-radius:999px;padding:1.5px 9px}}
.edu-meta{{color:#64748b;font-size:9.3pt;margin-top:2px}}
.edu-tags{{display:inline-flex;gap:4px;align-items:center}}
.edu-tag{{font-size:7.8pt;font-weight:700;color:{accent};background:{accent}12;
border:1px solid {accent}33;border-radius:999px;padding:1px 8px;letter-spacing:.6px;white-space:nowrap}}
ul.bullets{{margin:5px 0 0;padding-left:17px}}
ul.bullets li{{margin:3px 0;color:#374151;padding-left:2px}}
ul.bullets li::marker{{color:{accent}}}
.skills{{display:flex;flex-wrap:wrap;gap:7px}}
.skill-tag{{font-size:9pt;color:#334155;background:#f8fafc;border:1px solid {accent}2b;
border-radius:999px;padding:3.5px 13px}}
"""
    body = (
        f'<div class="topbar"></div><header><div class="head-main"><h1>{name}</h1>'
        f'<div class="name-accent"></div>'
        f'<div class="contact">{contact_html}</div>'
        + (f'<div class="x-row">{extra_html}</div>' if extra_html else "")
        + f"{summary_html}</div>{photo_html}</header>"
        + "".join(body_sections)
    )
    return _page_wrap(f"{name} - Resume", css, body, c["margin"], c["font_family"], c["font_size"], c["line_height"])


# ---------------------------------------------------------------- 模板 2：极简雅致
def render_minimal_ink(resume: dict, template: dict, layout: dict | None = None) -> str:
    c = _layout_common(template, layout)
    basics = resume.get("basics") or {}
    name = escape_html(basics.get("name") or "")
    summary = str(basics.get("summary") or "").strip()
    contacts = _contact_items(basics)
    extras = _extra_items(basics)
    skills = [str(x).strip() for x in (resume.get("skills") or []) if str(x).strip()]

    contact_line = "".join(
        f'<span class="c-item">{escape_html(v)}</span>' for _, v in contacts
    )
    extra_line = "　·　".join(f"{escape_html(v)}" for _, v in extras)
    summary_html = f'<p class="summary">{format_inline(summary)}</p>' if summary else ""

    body_sections = []
    sec_counter = [0]

    def numbered_section(title: str, inner: str) -> str:
        sec_counter[0] += 1
        return (
            f'<section><h2><span class="sec-num">{sec_counter[0]:02d}</span>'
            f'<span class="sec-tt">{title}</span></h2>{inner}</section>'
        )

    edu = _edu_rows(resume)
    if edu:
        rows = "".join(
            f'<div class="entry"><div class="entry-head"><span class="entry-title">{escape_html(e["school"])}</span>'
            f'{e["tags_html"]}'
            f'<span class="period">{escape_html(e["time"])}</span></div>'
            + (f'<div class="edu-meta">{escape_html(e["meta"])}</div>' if e["meta"] else "")
            + _bullet_html(e["bullets"])
            + "</div>"
            for e in edu
        )
        body_sections.append(numbered_section("教育经历", rows))
    for sec in _section_rows(resume):
        rows = "".join(_entry_block(it) for it in sec["items"])
        body_sections.append(numbered_section(escape_html(sec["title"]), rows))
    if skills:
        body_sections.append(numbered_section("技能", f"<p class='skill-line'>{'　·　'.join(escape_html(s) for s in skills)}</p>"))

    css = """
header{text-align:center;margin-bottom:6px}
h1{margin:0 0 10px;font-size:28pt;font-weight:600;letter-spacing:9px;color:#14161d;text-indent:9px}
.hairline{width:48px;height:2px;background:linear-gradient(90deg,transparent,#14161d,transparent);margin:0 auto 13px}
.contact{display:flex;justify-content:center;flex-wrap:wrap;gap:4px 0;font-size:9.5pt;color:#4a4f5e}
.c-item{display:inline-flex;align-items:center}
.c-item + .c-item::before{content:"·";margin:0 10px;color:#c3c7d3}
.extra{margin-top:5px;font-size:9pt;color:#8a8fa3;text-align:center}
.summary{text-align:center;color:#404554;max-width:88%;margin:16px auto 0;font-size:9.8pt;line-height:1.75}
section{margin-top:21px}
h2{display:flex;align-items:center;gap:13px;margin:0 0 11px;font-size:10.5pt;font-weight:700;
letter-spacing:5px;color:#14161d;text-transform:none}
h2::before,h2::after{content:"";flex:1;height:1px;background:#dcdfe8}
.sec-num{font-size:8.5pt;font-weight:600;letter-spacing:1px;color:#a3a8ba;font-variant-numeric:tabular-nums}
.sec-tt{letter-spacing:5px}
.entry{margin-bottom:10px}
.entry-head{display:flex;align-items:baseline;gap:9px}
.entry-title{font-weight:700;color:#16181f}
.org{color:#6b7280;font-size:9.5pt}
.period{margin-left:auto;color:#828798;font-size:9pt;white-space:nowrap;font-variant-numeric:tabular-nums}
.edu-meta{color:#6b7280;font-size:9.3pt;margin-top:2px}
.edu-tags{display:inline-flex;gap:4px;align-items:center}
.edu-tag{font-size:7.8pt;font-weight:700;color:#4b5563;background:#f4f5f7;
border:1px solid #d9dce4;border-radius:999px;padding:1px 8px;letter-spacing:.6px;white-space:nowrap}
ul.bullets{margin:5px 0 0;padding-left:15px;list-style:none}
ul.bullets li{margin:3.5px 0;color:#3c4152;position:relative;padding-left:3px}
ul.bullets li::before{content:"–";position:absolute;left:-13px;color:#a3a8ba}
.skill-line{margin:0;text-align:center;color:#3c4152;letter-spacing:.4px}
"""
    body = (
        f"<header><h1>{name}</h1><div class='hairline'></div><div class='contact'>{contact_line}</div>"
        + (f"<div class='extra'>{extra_line}</div>" if extra_line else "")
        + f"</header>{summary_html}"
        + "".join(body_sections)
    )
    return _page_wrap(f"{name} - Resume", css, body, c["margin"], c["font_family"], c["font_size"], c["line_height"])


# ---------------------------------------------------------------- 模板 3：双栏精英
def render_dual_column(resume: dict, template: dict, layout: dict | None = None) -> str:
    c = _layout_common(template, layout)
    accent = c["accent"]
    basics = resume.get("basics") or {}
    name = escape_html(basics.get("name") or "")
    summary = str(basics.get("summary") or "").strip()
    contacts = _contact_items(basics)
    extras = _extra_items(basics)
    photo = _photo_src(basics)
    skills = [str(x).strip() for x in (resume.get("skills") or []) if str(x).strip()]

    side_contact = "".join(
        f'<div class="s-item"><span class="s-ic">{ic}</span><span>{escape_html(v)}</span></div>' for ic, v in contacts
    )
    side_extra = "".join(
        f'<div class="s-item"><span class="s-ic">{ic}</span><span>{escape_html(v)}</span></div>' for ic, v in extras
    )
    side_skills = "".join(f"<li>{escape_html(s)}</li>" for s in skills)
    photo_html = f'<img class="avatar" src="{escape_html(photo)}" alt="" />' if photo else ""

    main_sections = []
    edu = _edu_rows(resume)
    if edu:
        rows = "".join(
            f'<div class="entry"><div class="entry-head"><span class="entry-title">{escape_html(e["school"])}</span>'
            f'{e["tags_html"]}'
            f'<span class="period">{escape_html(e["time"])}</span></div>'
            + (f'<div class="edu-meta">{escape_html(e["meta"])}</div>' if e["meta"] else "")
            + _bullet_html(e["bullets"])
            + "</div>"
            for e in edu
        )
        main_sections.append(f'<section><h2>教育经历</h2>{rows}</section>')
    for sec in _section_rows(resume):
        rows = "".join(_entry_block(it) for it in sec["items"])
        main_sections.append(f"<section><h2>{escape_html(sec['title'])}</h2>{rows}</section>")

    sidebar = (
        f'<aside>{photo_html}'
        + (f'<div class="s-sec"><div class="s-title">联系方式</div>{side_contact}</div>' if side_contact else "")
        + (f'<div class="s-sec"><div class="s-title">附加信息</div>{side_extra}</div>' if side_extra else "")
        + (f'<div class="s-sec"><div class="s-title">技能</div><ul class="s-skills">{side_skills}</ul></div>' if side_skills else "")
        + "</aside>"
    )
    summary_html = f'<p class="summary">{format_inline(summary)}</p>' if summary else ""
    main = f'<div class="main"><h1>{name}</h1><div class="name-accent"></div>{summary_html}{"".join(main_sections)}</div>'

    css = f"""
body{{display:flex;align-items:stretch}}
aside{{flex:0 0 62mm;background:linear-gradient(168deg,#0f1629 0%,#182140 52%,#202b52 100%);
color:#e8eaf2;padding:20px 15px;margin:-{c['margin']};margin-right:0;
padding-top:calc({c['margin']} + 18px);min-height:297mm}}
.avatar{{width:100%;aspect-ratio:3/4;object-fit:cover;border-radius:12px;
border:2px solid rgba(255,255,255,.22);margin-bottom:18px;box-shadow:0 6px 18px rgba(0,0,0,.35)}}
.s-sec{{margin-top:19px}}
.s-title{{display:flex;align-items:center;gap:7px;font-size:9.5pt;font-weight:700;letter-spacing:3px;color:#fff;opacity:.96;
border-bottom:1px solid rgba(255,255,255,.18);padding-bottom:7px;margin-bottom:10px}}
.s-title::before{{content:"";width:6px;height:6px;background:{accent};transform:rotate(45deg);
box-shadow:0 0 6px {accent}aa;flex:0 0 auto}}
.s-item{{display:flex;gap:8px;align-items:flex-start;font-size:8.8pt;line-height:1.6;
margin-bottom:6px;color:#d7dbea;word-break:break-all}}
.s-ic{{flex:0 0 auto;opacity:.9}}
ul.s-skills{{margin:0;padding-left:4px;list-style:none}}
ul.s-skills li{{position:relative;font-size:8.8pt;margin:5px 0;color:#d7dbea;padding-left:14px}}
ul.s-skills li::before{{content:"";position:absolute;left:2px;top:.55em;width:5px;height:5px;
border-radius:50%;background:{accent};filter:brightness(1.7);box-shadow:0 0 5px {accent}99}}
.main{{flex:1;min-width:0;padding-left:18px}}
h1{{margin:0 0 7px;font-size:22pt;font-weight:800;color:#0f172a;letter-spacing:1px}}
.name-accent{{width:52px;height:3.5px;border-radius:2px;background:{accent};margin:0 0 9px}}
.summary{{color:#475569;margin:4px 0 0;font-size:9.8pt;line-height:1.68}}
section{{margin-top:15px}}
h2{{margin:0 0 9px;font-size:11.5pt;font-weight:800;color:{accent};
display:flex;align-items:center;gap:9px;letter-spacing:1px}}
h2::before{{content:"";width:7px;height:7px;background:{accent};transform:rotate(45deg);flex:0 0 auto}}
h2::after{{content:"";flex:1;height:1px;background:linear-gradient(90deg,#e2e8f0,transparent)}}
.entry{{margin-bottom:10px}}
.entry-head{{display:flex;align-items:baseline;gap:9px}}
.entry-title{{font-weight:700;color:#0f172a}}
.org{{color:#64748b;font-size:9.5pt}}
.period{{margin-left:auto;color:#64748b;font-size:8.6pt;white-space:nowrap;
font-variant-numeric:tabular-nums;background:#f1f5f9;border-radius:999px;padding:1.5px 9px}}
.edu-meta{{color:#64748b;font-size:9.3pt;margin-top:2px}}
.edu-tags{{display:inline-flex;gap:4px;align-items:center}}
.edu-tag{{font-size:7.8pt;font-weight:700;color:{accent};background:{accent}12;
border:1px solid {accent}33;border-radius:999px;padding:1px 8px;letter-spacing:.6px;white-space:nowrap}}
ul.bullets{{margin:5px 0 0;padding-left:17px}}
ul.bullets li{{margin:3px 0;color:#374151;padding-left:2px}}
ul.bullets li::marker{{color:{accent}}}
"""
    body = sidebar + main
    return _page_wrap(f"{name} - Resume", css, body, c["margin"], c["font_family"], c["font_size"], c["line_height"])
