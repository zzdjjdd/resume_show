/* ============================================================
   Resume Agent · Studio 工作台
   复刻原项目 resume-form.tsx 核心能力：档案管理、角色档案（头像/附加信息）、
   教育经历、内容模块（拖拽/排序/显示开关）、技能、版式工具栏、
   实时预览、保存、PDF 导出、AI 润色（弹窗 + 前后对比）。
   ============================================================ */
(() => {
  "use strict";

  const API = "";
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));

  const DEGREE_OPTIONS = ["中专", "大专", "本科", "硕士", "博士", "MBA"];
  const ICON_OPTIONS = [
    { v: "💼", l: "求职/职业" }, { v: "🎯", l: "目标/意向" }, { v: "🔗", l: "链接/网站" },
    { v: "🔬", l: "研究/学术" }, { v: "🧭", l: "方向/定位" }, { v: "⭐", l: "亮点/其他" },
  ];
  const ACCENT_PRESETS = ["#4f46e5", "#7c3aed", "#1e40af", "#b42318", "#0f766e", "#1f2937"];
  const DEFAULT_LAYOUT = {
    pageMarginMm: 14, bodyFontSizePt: 10.5, lineHeight: 1.45, headerStyle: "default",
    accentColor: "#4f46e5", fontFamily: "'Source Han Sans SC','Noto Sans SC','PingFang SC','Hiragino Sans GB','Microsoft YaHei','微软雅黑',sans-serif",
    sectionTitles: { skills: "技能" },
  };
  const PHOTO_MAX = 2 * 1024 * 1024;
  const uid = () => Math.random().toString(36).slice(2, 9);
  const esc = (s) => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");

  /* ---------------- 状态 ---------------- */
  const state = {
    files: [], fileId: null, record: null,
    basics: { name: "", email: "", phone: "", location: "", summary: "", photo: "" },
    extraInfos: [],           // [{id,label,value,icon}]
    education: [],            // [{id,school,degree,major,gpa,college,startDate,endDate,schoolTags,summary}]
    sections: [],             // [{id,title,enabled,items:[{id,title,org,period,bullets}]}]
    showSkills: true, skills: "",
    config: { templateId: "modern-pro", layout: { ...DEFAULT_LAYOUT } },
    debounce: null, drag: null,
    polish: { targets: [], selected: [], results: {}, snapshot: [], activeId: "" },
  };

  /* ---------------- 通用 ---------------- */
  async function api(path, opt = {}) {
    const r = await fetch(`${API}${path}`, { headers: { "Content-Type": "application/json" }, ...opt });
    const text = await r.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch { data = text; }
    if (!r.ok) {
      if (r.status === 413) throw new Error("内容过大（如头像过大），请压缩图片后重试");
      throw new Error((data && data.detail) || `请求失败（${r.status}）`);
    }
    return data;
  }
  function setStatus(text, kind) {
    const pill = $("#save-status");
    $("#save-status-text").textContent = text;
    pill.className = "save-pill" + (kind ? ` ${kind}` : "");
  }
  function confirmDel(name) { return window.confirm(`确定删除 ${name} 吗？`); }

  /* ---------------- 数据映射（与后端 Resume 结构互转） ---------------- */
  function readResume() {
    return {
      basics: {
        name: state.basics.name, email: state.basics.email, phone: state.basics.phone,
        location: state.basics.location, summary: state.basics.summary,
        photo: state.basics.photo || undefined,
        extraInfos: state.extraInfos
          .map((x) => ({ label: x.label.trim(), value: x.value.trim(), icon: x.icon.trim() || undefined }))
          .filter((x) => x.label || x.value),
      },
      education: state.education
        .map((e) => {
          const summaryLines = e.summary.split("\n").map((s) => s.trim()).filter(Boolean);
          const out = {
            school: e.school.trim(), degree: e.degree.trim() || "本科", major: e.major.trim(),
            startDate: e.startDate.trim(), endDate: e.endDate.trim(),
            gpa: e.gpa.trim() || undefined, schoolTags: e.schoolTags.trim() || undefined,
            college: e.college.trim() || undefined, summary: e.summary.trim() || undefined,
          };
          const hl = [e.schoolTags.trim() ? `学校标签: ${e.schoolTags.trim()}` : "", ...summaryLines].filter(Boolean);
          if (hl.length) out.highlights = hl;
          return out;
        })
        .filter((e) => e.school || e.major || e.startDate || e.endDate || e.gpa || e.schoolTags || e.college || e.summary),
      customSections: state.sections.filter((s) => s.enabled).map((s) => ({
        title: s.title.trim() || "未命名模块",
        items: s.items
          .filter((i) => i.title.trim() || i.org.trim() || i.period.trim() || i.bullets.split("\n").some((x) => x.trim()))
          .map((i) => ({
            title: i.title.trim(), org: i.org.trim(), period: i.period.trim(),
            highlights: i.bullets.split("\n").map((x) => x.trim()).filter(Boolean),
          })),
      })),
      skills: state.showSkills ? state.skills.split(/[,，、]/).map((s) => s.trim()).filter(Boolean) : [],
    };
  }

  function applyResume(resume) {
    const b = resume.basics || {};
    state.basics = {
      name: b.name || "", email: b.email || "", phone: b.phone || "",
      location: b.location || "", summary: b.summary || "", photo: b.photo || "",
    };
    state.extraInfos = (b.extraInfos || []).map((x) => ({
      id: uid(), label: x.label || "", value: x.value || "", icon: x.icon || "⭐",
    }));
    state.education = (resume.education || []).map((e) => {
      const hl = Array.isArray(e.highlights) ? e.highlights.map(String) : [];
      const tagFromHl = (hl.find((l) => l.startsWith("学校标签:")) || "").slice(5).trim();
      const summaryLines = hl.filter((l) => !l.startsWith("GPA:") && !l.startsWith("所在学院:") && !l.startsWith("学校标签:")).map((l) => (l.startsWith("简介:") ? l.slice(3).trim() : l)).filter(Boolean);
      return {
        id: uid(), school: e.school || "", degree: e.degree || "本科", major: e.major || "",
        gpa: e.gpa || "", college: e.college || "", startDate: e.startDate || "", endDate: e.endDate || "",
        schoolTags: (e.schoolTags || "").trim() || tagFromHl,
        summary: (e.summary || "").trim() || summaryLines.join("\n"),
      };
    });
    if (!state.education.length) state.education = [newEdu()];
    const secs = (resume.customSections || []).map((s) => ({
      id: uid(), title: s.title || "未命名模块", enabled: true,
      items: ((s.items || []).length ? s.items : [{ title: "", org: "", period: "", highlights: [] }]).map((i) => ({
        id: uid(), title: i.title || "", org: i.org || "", period: i.period || "",
        bullets: (i.highlights || []).join("\n"),
      })),
    }));
    state.sections = secs.length ? secs : defaultSections();
    const sk = Array.isArray(resume.skills) ? resume.skills : [];
    state.showSkills = sk.length > 0;
    state.skills = sk.join(", ");
  }

  function newEdu() {
    return { id: uid(), school: "", degree: "本科", major: "", gpa: "", college: "", startDate: "", endDate: "", schoolTags: "", summary: "" };
  }
  function newItem() { return { id: uid(), title: "", org: "", period: "", bullets: "" }; }
  function defaultSections() {
    return [
      { id: uid(), title: "工作/实习经历", enabled: true, items: [{ id: uid(), title: "前端工程师", org: "某科技公司", period: "2022-07 ~ 至今", bullets: "负责核心页面重构\n首屏性能提升 40%\n沉淀组件库规范" }] },
      { id: uid(), title: "项目经历", enabled: true, items: [{ id: uid(), title: "简历 Agent 平台", org: "个人项目", period: "2026", bullets: "支持模板切换与 PDF 导出\n支持简历润色与模拟面试" }] },
      { id: uid(), title: "科研/校园经历", enabled: true, items: [{ id: uid(), title: "多模态简历评估研究", org: "实验室", period: "2025", bullets: "建立简历质量评估指标\n完成 A/B 测试分析" }] },
    ];
  }

  /* ---------------- Markdown 文本域（B/I/U/列表快捷键） ---------------- */
  function wrapSel(el, marker) {
    const v = el.value, s = el.selectionStart || 0, e = el.selectionEnd || s;
    const sel = v.slice(s, e);
    el.value = v.slice(0, s) + marker + sel + marker + v.slice(e);
    el.focus(); el.setSelectionRange(s + marker.length, s + marker.length + sel.length);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }
  function toggleList(el, kind) {
    const v = el.value, s = el.selectionStart || 0, e = el.selectionEnd || s;
    const ls = v.lastIndexOf("\n", Math.max(0, s - 1)) + 1;
    const leRaw = v.indexOf("\n", e), le = leRaw === -1 ? v.length : leRaw;
    const lines = v.slice(ls, le).split("\n");
    const re = kind === "ul" ? /^(\s*)[-*+]\s+(.*)$/ : /^(\s*)(\d+)[.)]\s+(.*)$/;
    const all = lines.filter((l) => l.trim()).every((l) => re.test(l));
    let n = 0;
    const next = lines.map((l) => {
      if (!l.trim()) return l;
      const m = l.match(/^(\s*)[-*+]\s+(.*)$/) || l.match(/^(\s*)(\d+)[.)]\s+(.*)$/);
      const indent = m ? m[1] : ""; const text = m ? (m[3] != null ? m[3] : m[2]) : l.trim();
      if (all) return indent + text;
      n++; return kind === "ul" ? `${indent}- ${text}` : `${indent}${n}. ${text}`;
    }).join("\n");
    el.value = v.slice(0, ls) + next + v.slice(le);
    el.focus(); el.setSelectionRange(ls, ls + next.length);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }
  function mdToolbar() {
    return `<div class="md-tools">
      <button class="md-b b" data-md="**" type="button" title="加粗 Ctrl+B">B</button>
      <button class="md-b i" data-md="*" type="button" title="斜体 Ctrl+I">I</button>
      <button class="md-b u" data-md="__" type="button" title="下划线 Ctrl+U">U</button>
      <button class="md-b" data-list="ul" type="button" title="无序列表">•</button>
      <button class="md-b" data-list="ol" type="button" title="有序列表">1.</button>
    </div>`;
  }
  // md 工具按钮样式（注入一次）
  const mdCss = document.createElement("style");
  mdCss.textContent = `.md-wrap{position:relative}.md-tools{display:flex;gap:4px;position:absolute;right:8px;top:8px;z-index:2}
    .md-b{min-width:24px;height:22px;border:1px solid var(--line);background:var(--panel);border-radius:6px;font-size:11px;font-weight:800;color:var(--ink-2);cursor:pointer;padding:0 5px}
    .md-b:hover{color:var(--accent);border-color:var(--accent)}.md-b.b{font-weight:900}.md-b.i{font-style:italic}.md-b.u{text-decoration:underline}`;
  document.head.appendChild(mdCss);
  function bindMd(ta) {
    const wrap = document.createElement("div");
    wrap.className = "md-wrap";
    ta.parentNode.insertBefore(wrap, ta);
    wrap.appendChild(ta);
    wrap.insertAdjacentHTML("beforeend", mdToolbar());
    ta.style.paddingTop = "10px";
    wrap.querySelectorAll(".md-b").forEach((btn) => {
      btn.addEventListener("mousedown", (e) => {
        e.preventDefault();
        if (btn.dataset.md) wrapSel(ta, btn.dataset.md);
        else toggleList(ta, btn.dataset.list);
      });
    });
    ta.addEventListener("keydown", (e) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      const k = e.key.toLowerCase();
      const map = { b: "**", i: "*", u: "__" };
      if (map[k]) { e.preventDefault(); wrapSel(ta, map[k]); }
    });
  }

  /* ---------------- 渲染 ---------------- */
  function renderAll() {
    renderFiles(); renderProfile(); renderEdu(); renderSections(); renderSkills(); renderLayoutForm(); renderTplList();
  }

  function renderFiles() {
    const wrap = $("#file-list");
    if (!state.files.length) { wrap.innerHTML = '<div class="file-empty">暂无档案文件</div>'; return; }
    wrap.innerHTML = state.files.map((f) => `
      <div class="file-item ${f.id === state.fileId ? "active" : ""}" data-id="${f.id}">
        <div class="file-top">
          <span class="file-dot"></span>
          <span class="file-name" title="${esc(f.name)}">${esc(f.name)}</span>
          ${f.isDefault ? '<span class="badge badge-def">默认</span>' : ""}
          ${f.id === state.fileId ? '<span class="badge badge-cur">当前</span>' : ""}
        </div>
        <div class="file-meta">更新于 ${(f.updatedAt || "").slice(0, 10)}</div>
        <div class="file-ops">
          <button class="file-op" data-act="open" type="button">打开</button>
          <button class="file-op" data-act="rename" type="button">重命名</button>
          <button class="file-op" data-act="default" type="button">设默认</button>
          <button class="file-op danger" data-act="delete" type="button">删除</button>
        </div>
      </div>`).join("");
  }

  function renderProfile() {
    $("#basics-name").value = state.basics.name;
    $("#basics-email").value = state.basics.email;
    $("#basics-phone").value = state.basics.phone;
    $("#basics-location").value = state.basics.location;
    $("#basics-summary").value = state.basics.summary;
    const pp = $("#photo-preview");
    pp.innerHTML = state.basics.photo
      ? `<img src="${state.basics.photo}" alt="头像" />`
      : '<span class="photo-empty">头像</span>';
    $("#btn-photo-del").disabled = !state.basics.photo;
    $("#extra-list").innerHTML = state.extraInfos.map((x, i) => `
      <div class="extra-row">
        <select class="ipt ex-icon" data-i="${i}">
          ${ICON_OPTIONS.map((o) => `<option value="${o.v}" ${x.icon === o.v ? "selected" : ""}>${o.v} ${o.l}</option>`).join("")}
        </select>
        <input class="ipt ex-label" data-i="${i}" value="${esc(x.label)}" placeholder="字段名" />
        <input class="ipt ex-value" data-i="${i}" value="${esc(x.value)}" placeholder="字段值" />
        <button class="icon-btn danger ex-del" data-i="${i}" type="button" title="删除">✕</button>
      </div>`).join("");
  }

  function renderEdu() {
    const wrap = $("#edu-list");
    wrap.innerHTML = state.education.map((e, idx) => `
      <div class="entry" data-edu="${idx}" draggable="false">
        <div class="entry-head">
          <span class="drag-handle" data-drag="edu" data-i="${idx}" title="拖动排序">⠿</span>
          <span class="entry-tag">教育 ${idx + 1}</span>
          <span style="flex:1"></span>
          <span class="entry-actions">
            <button class="icon-btn" data-edu-act="up" data-i="${idx}" ${idx === 0 ? "disabled" : ""} title="上移">↑</button>
            <button class="icon-btn" data-edu-act="down" data-i="${idx}" ${idx === state.education.length - 1 ? "disabled" : ""} title="下移">↓</button>
            <button class="icon-btn danger" data-edu-act="del" data-i="${idx}" title="删除">🗑</button>
          </span>
        </div>
        <div class="entry-grid">
          <input class="ipt" data-f="school" data-i="${idx}" value="${esc(e.school)}" placeholder="学校" />
          <select class="ipt" data-f="degree" data-i="${idx}">
            ${DEGREE_OPTIONS.map((d) => `<option value="${d}" ${e.degree === d ? "selected" : ""}>${d}</option>`).join("")}
          </select>
          <input class="ipt" data-f="major" data-i="${idx}" value="${esc(e.major)}" placeholder="专业" />
          <input class="ipt" data-f="gpa" data-i="${idx}" value="${esc(e.gpa)}" placeholder="GPA" />
          <input class="ipt" data-f="college" data-i="${idx}" value="${esc(e.college)}" placeholder="所在学院" />
          <input class="ipt" data-f="schoolTags" data-i="${idx}" value="${esc(e.schoolTags)}" placeholder="学校标签（985/211/双一流）" />
          <input class="ipt" data-f="startDate" data-i="${idx}" value="${esc(e.startDate)}" placeholder="开始时间 2022-09" />
          <input class="ipt" data-f="endDate" data-i="${idx}" value="${esc(e.endDate)}" placeholder="结束时间 2026-06" />
        </div>
        <textarea class="ipt ta edu-summary" data-i="${idx}" rows="2" placeholder="教育亮点 / 简介（每行一条）">${esc(e.summary)}</textarea>
      </div>`).join("");
    wrap.querySelectorAll(".edu-summary").forEach(bindMd);
  }

  function renderSections() {
    const wrap = $("#section-list");
    wrap.innerHTML = state.sections.map((s, si) => `
      <div class="section-box" data-sec="${si}">
        <div class="section-head">
          <span class="drag-handle" data-drag="sec" data-i="${si}" title="拖动模块排序">⠿</span>
          <input class="ipt sec-title" data-i="${si}" value="${esc(s.title)}" placeholder="模块标题" />
          <label class="switch"><input type="checkbox" data-sec-show="${si}" ${s.enabled ? "checked" : ""} /><span class="switch-track"></span><span class="switch-text">显示</span></label>
          <button class="icon-btn" data-sec-act="up" data-i="${si}" ${si === 0 ? "disabled" : ""} title="上移模块">↑</button>
          <button class="icon-btn" data-sec-act="down" data-i="${si}" ${si === state.sections.length - 1 ? "disabled" : ""} title="下移模块">↓</button>
          <button class="icon-btn danger" data-sec-act="del" data-i="${si}" title="删除模块">🗑</button>
        </div>
        <div class="section-body ${s.enabled ? "" : "hidden-sec"}">
          ${s.items.map((it, ii) => `
            <div class="entry" data-item="${si}-${ii}">
              <div class="entry-head">
                <span class="drag-handle" data-drag="item" data-si="${si}" data-i="${ii}" title="拖动条目排序">⠿</span>
                <span class="entry-tag">条目 ${ii + 1}</span>
                <span style="flex:1"></span>
                <span class="entry-actions">
                  <button class="icon-btn" data-item-act="up" data-si="${si}" data-i="${ii}" ${ii === 0 ? "disabled" : ""}>↑</button>
                  <button class="icon-btn" data-item-act="down" data-si="${si}" data-i="${ii}" ${ii === s.items.length - 1 ? "disabled" : ""}>↓</button>
                  <button class="icon-btn danger" data-item-act="del" data-si="${si}" data-i="${ii}">🗑</button>
                </span>
              </div>
              <div class="entry-grid c3">
                <input class="ipt" data-if="title" data-si="${si}" data-i="${ii}" value="${esc(it.title)}" placeholder="标题 / 职位" />
                <input class="ipt" data-if="org" data-si="${si}" data-i="${ii}" value="${esc(it.org)}" placeholder="组织 / 公司" />
                <input class="ipt" data-if="period" data-si="${si}" data-i="${ii}" value="${esc(it.period)}" placeholder="时间" />
              </div>
              <textarea class="ipt ta item-bullets" data-si="${si}" data-i="${ii}" rows="3" placeholder="要点（每行一条，支持 **加粗** 与列表）">${esc(it.bullets)}</textarea>
            </div>`).join("")}
          <button class="mini-btn item-add" data-si="${si}" type="button">＋ 新增条目</button>
        </div>
      </div>`).join("");
    wrap.querySelectorAll(".item-bullets").forEach(bindMd);
  }

  function renderSkills() {
    $("#skills-show").checked = state.showSkills;
    $("#skills-input").value = state.skills;
    $("#skills-input").disabled = !state.showSkills;
  }

  function renderLayoutForm() {
    const l = state.config.layout;
    const preset = $("#accent-preset");
    preset.value = ACCENT_PRESETS.includes(l.accentColor) ? l.accentColor : ACCENT_PRESETS[0];
    $("#layout-accent").value = l.accentColor;
    $("#layout-font").value = l.fontFamily;
    $("#layout-headerstyle").value = l.headerStyle;
    $("#layout-margin").value = String(l.pageMarginMm);
    $("#layout-fontsize").value = l.bodyFontSizePt;
    $("#fontsize-val").textContent = `${Number(l.bodyFontSizePt).toFixed(1)} pt`;
    $("#layout-lineheight").value = l.lineHeight;
    $("#lineheight-val").textContent = Number(l.lineHeight).toFixed(2);
  }

  /* ---------------- 文件操作 ---------------- */
  async function loadFiles(preferId) {
    state.files = await api("/resume-files");
    const pick = preferId && state.files.some((f) => f.id === preferId) ? preferId
      : (state.fileId && state.files.some((f) => f.id === state.fileId)) ? state.fileId
      : (state.files.find((f) => f.isDefault) || state.files[0] || {}).id || null;
    state.fileId = pick;
    renderFiles();
    return pick;
  }
  async function loadFile(id) {
    const rec = await api(`/resume-files/${id}`);
    state.record = rec; state.fileId = rec.id;
    state.config = {
      templateId: (rec.config || {}).templateId || "modern-pro",
      layout: { ...DEFAULT_LAYOUT, ...((rec.config || {}).layout || {}), sectionTitles: { ...DEFAULT_LAYOUT.sectionTitles, ...(((rec.config || {}).layout || {}).sectionTitles || {}) } },
    };
    applyResume(rec.data || {});
    renderAll();
    setStatus("就绪");
  }
  async function newFile() {
    const name = window.prompt("请输入新简历文件名（可留空）", "");
    if (name === null) return;
    try {
      const rec = await api("/resume-files", { method: "POST", body: JSON.stringify({ name: name.trim() || undefined, config: state.config }) });
      await loadFiles(rec.id); await loadFile(rec.id);
    } catch (e) { setStatus(e.message, "err"); }
  }
  async function renameFile(id) {
    const f = state.files.find((x) => x.id === id); if (!f) return;
    const name = window.prompt("新的名称：", f.name);
    if (!name || !name.trim()) return;
    try { await api(`/resume-files/${id}`, { method: "PATCH", body: JSON.stringify({ name: name.trim() }) }); await loadFiles(state.fileId); }
    catch (e) { setStatus(e.message, "err"); }
  }
  async function setDefaultFile(id) {
    try { await api(`/resume-files/${id}/default`, { method: "PATCH", body: "{}" }); await loadFiles(state.fileId); }
    catch (e) { setStatus(e.message, "err"); }
  }
  async function deleteFile(id) {
    const f = state.files.find((x) => x.id === id); if (!f) return;
    if (state.files.length <= 1) { setStatus("至少保留一份简历文件", "err"); return; }
    if (!confirmDel(`简历文件「${f.name}」`)) return;
    try {
      const res = await api(`/resume-files/${id}`, { method: "DELETE" });
      const nextId = await loadFiles(res.nextDefaultId || undefined);
      if (nextId) await loadFile(nextId);
    } catch (e) { setStatus(e.message, "err"); }
  }

  /* ---------------- 预览弹窗 / 保存 / PDF ---------------- */
  async function generateResumeHtml(templateId) {
    const r = await fetch(`${API}/export/html`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ resume: readResume(), templateId: templateId || state.config.templateId, layout: state.config.layout }),
    });
    if (!r.ok) throw new Error(`预览生成失败（${r.status}）`);
    return r.text();
  }
  function fitPvFrame(frame) {
    try {
      const d = frame.contentDocument;
      if (!d || !d.body) return;
      const h = Math.max(
        d.body.scrollHeight, d.documentElement.scrollHeight,
        d.body.offsetHeight, d.documentElement.offsetHeight
      );
      if (h > 0) frame.style.height = (h + 2) + "px";
    } catch (e) { /* ignore */ }
  }
  async function renderPvFrame(templateId) {
    const frame = $("#pv-frame");
    const html = await generateResumeHtml(templateId);
    // 注入 body padding 使其与 PDF 页边距一致，屏幕预览与 PDF 排版对齐
    const margin = state.config.layout.pageMarginMm || 14;
    const styled = html.replace("</head>", `<style>body{padding:${margin}mm;background:#fff}</style></head>`);
    frame.srcdoc = styled;
    const refit = () => fitPvFrame(frame);
    frame.onload = () => { refit(); setTimeout(refit, 250); setTimeout(refit, 900); };
    setTimeout(refit, 500);
  }
  function renderPvTplSelect() {
    const sel = $("#pv-tpl");
    const list = templatesCache.length ? templatesCache : [{ id: state.config.templateId, name: "当前模板" }];
    sel.innerHTML = list.map((t) =>
      `<option value="${t.id}" ${t.id === state.config.templateId ? "selected" : ""}>${esc(t.name)}</option>`
    ).join("");
  }
  async function openPreview() {
    const modal = $("#preview-modal");
    modal.classList.remove("hidden");
    renderPvTplSelect();
    try {
      await renderPvFrame();
    } catch (e) { setStatus(e.message, "err"); }
  }
  function closePreview() { $("#preview-modal").classList.add("hidden"); }
  function markDirty() {
    setStatus("有未保存更改…", "dirty");
  }
  async function save(silent) {
    if (!state.fileId) { setStatus("当前没有可保存的简历", "err"); return false; }
    if (!silent) setStatus("保存中…", "busy");
    try {
      const rec = await api(`/resume-files/${state.fileId}`, {
        method: "PUT",
        body: JSON.stringify({ resume: readResume(), config: state.config }),
      });
      state.record = rec;
      await loadFiles(rec.id);
      if (!silent) setStatus("已保存 ✓");
      return true;
    } catch (e) { setStatus(e.message, "err"); return false; }
  }
  async function exportPdf() {
    setStatus("导出 PDF…", "busy");
    try {
      const ok = await save(true);
      if (!ok) return;
      const r = await fetch(`${API}/export/pdf`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ resume: readResume(), templateId: state.config.templateId, layout: state.config.layout }),
      });
      if (!r.ok) throw new Error(`导出失败（${r.status}）`);
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `resume-${(state.basics.name || "export")}.pdf`;
      a.click(); URL.revokeObjectURL(url);
      setStatus("PDF 已导出 ✓");
    } catch (e) { setStatus(e.message, "err"); }
  }

  /* ---------------- AI 润色 ---------------- */
  function collectTargets() {
    const targets = [];
    state.sections.forEach((s) => {
      if (!s.enabled) return;
      if (/教育|校园|education/i.test(s.title)) return;
      s.items.forEach((it) => {
        if (!(it.title.trim() || it.org.trim() || it.period.trim() || it.bullets.trim())) return;
        targets.push({
          id: uid(), sectionTitle: s.title.trim() || "未命名模块",
          title: it.title.trim(), org: it.org.trim(), period: it.period.trim(), bullets: it.bullets.trim(),
        });
      });
    });
    if (state.showSkills && state.skills.trim()) {
      targets.push({ id: uid(), sectionTitle: "技能", title: "技能", org: "", period: "", bullets: state.skills.split(/[,，、]/).map((s) => s.trim()).filter(Boolean).join("\n") });
    }
    return targets;
  }
  function openPolish() {
    state.polish.targets = collectTargets();
    state.polish.selected = state.polish.targets.slice(0, 2).map((t) => t.id);
    state.polish.results = {};
    $("#polish-error").textContent = "";
    renderPolishTargets();
    $("#polish-modal").classList.remove("hidden");
  }
  function renderPolishTargets() {
    const wrap = $("#polish-targets");
    if (!state.polish.targets.length) { wrap.innerHTML = '<div class="pt-empty">未找到可润色条目（教育经历已排除）</div>'; return; }
    wrap.innerHTML = state.polish.targets.map((t) => `
      <label class="pt-item ${state.polish.selected.includes(t.id) ? "checked" : ""}">
        <input type="checkbox" data-pt="${t.id}" ${state.polish.selected.includes(t.id) ? "checked" : ""} />
        <span class="pt-sec">${esc(t.sectionTitle)}</span>
        <span class="pt-name">${esc(t.title || "未命名条目")}${t.org ? ` · ${esc(t.org)}` : ""}</span>
      </label>`).join("");
  }
  async function runPolish() {
    const selected = state.polish.targets.filter((t) => state.polish.selected.includes(t.id));
    if (!selected.length) { $("#polish-error").textContent = "请先选择至少一个条目"; return; }
    if (!window.LLMSettings.hasConfig()) {
      $("#polish-error").textContent = "请先在右上角「设置」中配置大模型";
      window.LLMSettings.open();
      return;
    }
    const btn = $("#polish-run");
    btn.disabled = true; btn.textContent = "润色中…";
    $("#polish-error").textContent = "";
    try {
      const body = window.LLMSettings.inject({
        resumeFileId: state.fileId || undefined, targetPosition: "目标岗位",
        jobDescription: $("#polish-jd").value.trim(), targets: selected,
      });
      const data = await api("/resume/polish", {
        method: "POST",
        body: JSON.stringify(body),
      });
      const map = {};
      (data.items || []).forEach((x) => { if (x && x.id) map[x.id] = x; });
      if (!Object.keys(map).length) throw new Error("模型未返回可用润色结果，请重试");
      state.polish.results = map;
      state.polish.snapshot = selected;
      state.polish.activeId = selected.find((x) => map[x.id])?.id || "";
      $("#polish-modal").classList.add("hidden");
      renderCompare();
    } catch (e) { $("#polish-error").textContent = e.message; }
    finally { btn.disabled = false; btn.textContent = "开始润色"; }
  }
  function renderCompare() {
    const panel = $("#polish-compare");
    panel.classList.remove("hidden");
    const sel = $("#pc-select");
    sel.innerHTML = state.polish.snapshot.filter((x) => state.polish.results[x.id])
      .map((x, i) => `<option value="${x.id}" ${x.id === state.polish.activeId ? "selected" : ""}>${i + 1}. [${esc(x.sectionTitle)}] ${esc(x.title || "未命名条目")}</option>`).join("");
    const before = state.polish.snapshot.find((x) => x.id === state.polish.activeId) || state.polish.snapshot.find((x) => state.polish.results[x.id]);
    const after = before ? state.polish.results[before.id] : null;
    if (!before || !after) { $("#pc-body").innerHTML = '<div class="pt-empty">暂无润色结果</div>'; return; }
    const beforeText = `${before.title}${before.org ? ` - ${before.org}` : ""}\n${before.period}\n${before.bullets}`.trim();
    const afterText = `${after.polishedTitle}${after.polishedOrg ? ` - ${after.polishedOrg}` : ""}\n${after.polishedPeriod}\n${after.polishedBullets}`.trim();
    $("#pc-body").innerHTML = `
      <div class="pc-cols">
        <div><span class="pc-col-title before">润色前</span><pre class="pc-pre">${esc(beforeText)}</pre></div>
        <div><span class="pc-col-title after">润色后</span><pre class="pc-pre">${esc(afterText)}</pre></div>
      </div>
      ${after.changeSummary ? `<div class="pc-note"><b>改动说明：</b>${esc(after.changeSummary)}</div>` : ""}
      ${after.jdRelevance === "none" ? '<div class="pc-note">与当前 JD 相关性低：仅做表达润色，不提供下一步建议。</div>' : ""}
      ${after.jdImprovements && after.jdImprovements.length ? `<div class="pc-note next"><b>下一步优化建议</b><ul>${after.jdImprovements.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>` : ""}`;
  }

  /* ---------------- 拖拽排序 ---------------- */
  function move(list, from, to) {
    if (from < 0 || from >= list.length || to < 0 || to >= list.length || from === to) return list;
    const next = [...list];
    const [p] = next.splice(from, 1);
    next.splice(to, 0, p);
    return next;
  }
  function bindDrag() {
    document.addEventListener("dragstart", (e) => {
      const h = e.target.closest?.("[data-drag]");
      if (!h) return;
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", "drag");
      state.drag = { group: h.dataset.drag, si: h.dataset.si != null ? +h.dataset.si : null, index: +h.dataset.i };
      const box = h.closest(".entry, .section-box");
      if (box) box.classList.add("dragging");
    });
    document.addEventListener("dragend", () => {
      state.drag = null;
      $$(".dragging").forEach((x) => x.classList.remove("dragging"));
      $$(".drag-over").forEach((x) => x.classList.remove("drag-over"));
    });
    document.addEventListener("dragover", (e) => {
      if (!state.drag) return;
      const d = state.drag;
      let target = null;
      if (d.group === "edu") target = e.target.closest?.("[data-edu]");
      if (d.group === "sec") target = e.target.closest?.("[data-sec]");
      if (d.group === "item") target = e.target.closest?.(`[data-item^="${d.si}-"]`);
      if (!target) return;
      e.preventDefault();
      $$(".drag-over").forEach((x) => x.classList.remove("drag-over"));
      target.classList.add("drag-over");
    });
    document.addEventListener("drop", (e) => {
      if (!state.drag) return;
      const d = state.drag;
      let to = null;
      if (d.group === "edu") { const t = e.target.closest?.("[data-edu]"); to = t ? +t.dataset.edu : null; }
      if (d.group === "sec") { const t = e.target.closest?.("[data-sec]"); to = t ? +t.dataset.sec : null; }
      if (d.group === "item") { const t = e.target.closest?.(`[data-item^="${d.si}-"]`); to = t ? +t.dataset.item.split("-")[1] : null; }
      if (to == null) return;
      e.preventDefault();
      if (d.group === "edu") state.education = move(state.education, d.index, to);
      if (d.group === "sec") state.sections = move(state.sections, d.index, to);
      if (d.group === "item") state.sections[d.si].items = move(state.sections[d.si].items, d.index, to);
      state.drag = null;
      if (d.group === "edu") renderEdu();
      if (d.group === "sec") renderSections();
      if (d.group === "item") renderSections();
      markDirty();
    });
    // 让拖柄本身可拖
    document.addEventListener("mousedown", () => {
      $$("[data-drag]").forEach((h) => { h.closest(".entry, .section-box")?.setAttribute("draggable", "true"); });
    });
    document.addEventListener("dragstart", (e) => {
      const box = e.target.closest?.(".entry, .section-box");
      if (box && !e.target.closest?.("[data-drag]")) { e.preventDefault(); }
    }, true);
  }

  /* ---------------- 事件绑定 ---------------- */
  function bind() {
    // 顶栏
    $("#btn-save").addEventListener("click", () => save(false));
    $("#btn-settings").addEventListener("click", () => window.LLMSettings.open());
    $("#btn-preview").addEventListener("click", openPreview);
    $("#btn-polish").addEventListener("click", openPolish);

    // 预览弹窗
    $("#pv-close").addEventListener("click", closePreview);
    $("#pv-pdf").addEventListener("click", exportPdf);
    $("#pv-tpl").addEventListener("change", (e) => {
      state.config.templateId = e.target.value;
      renderTplList();
      renderPvFrame(e.target.value);
    });
    $("#preview-modal").addEventListener("click", (e) => {
      if (e.target.id === "preview-modal") closePreview();
    });

    // 基础字段
    ["basics-name", "basics-email", "basics-phone", "basics-location"].forEach((id) => {
      $(`#${id}`).addEventListener("input", (e) => { state.basics[id.slice(7)] = e.target.value; markDirty(); });
    });
    $("#basics-summary").addEventListener("input", (e) => { state.basics.summary = e.target.value; markDirty(); });

    // 头像
    $("#btn-photo-pick").addEventListener("click", () => $("#photo-input").click());
    $("#photo-input").addEventListener("change", (e) => {
      const f = e.target.files?.[0]; e.target.value = "";
      if (!f) return;
      if (!f.type.startsWith("image/")) { setStatus("请选择图片格式的头像文件", "err"); return; }
      if (f.size > PHOTO_MAX) { setStatus("头像文件不能超过 2MB", "err"); return; }
      const reader = new FileReader();
      reader.onload = () => { state.basics.photo = String(reader.result || ""); renderProfile(); markDirty(); };
      reader.readAsDataURL(f);
    });
    $("#btn-photo-del").addEventListener("click", () => {
      if (state.basics.photo && confirmDel("头像照片")) { state.basics.photo = ""; renderProfile(); markDirty(); }
    });

    // 附加信息
    $$(".chip-btn").forEach((b) => b.addEventListener("click", () => {
      state.extraInfos.push({ id: uid(), label: b.dataset.extraLabel, value: "", icon: b.dataset.extraIcon });
      renderProfile(); markDirty();
    }));
    $("#btn-add-extra").addEventListener("click", () => {
      state.extraInfos.push({ id: uid(), label: "", value: "", icon: "⭐" });
      renderProfile(); markDirty();
    });
    $("#extra-list").addEventListener("input", (e) => {
      const i = +e.target.dataset.i;
      if (e.target.classList.contains("ex-label")) state.extraInfos[i].label = e.target.value;
      if (e.target.classList.contains("ex-value")) state.extraInfos[i].value = e.target.value;
      if (e.target.classList.contains("ex-icon")) state.extraInfos[i].icon = e.target.value;
      markDirty();
    });
    $("#extra-list").addEventListener("click", (e) => {
      const del = e.target.closest(".ex-del"); if (!del) return;
      const i = +del.dataset.i;
      const name = state.extraInfos[i]?.label?.trim() || `附加信息第${i + 1}条`;
      if (!confirmDel(`附加信息「${name}」`)) return;
      state.extraInfos.splice(i, 1); renderProfile(); markDirty();
    });

    // 教育
    $("#btn-add-edu").addEventListener("click", () => { state.education.push(newEdu()); renderEdu(); markDirty(); });
    $("#edu-list").addEventListener("input", (e) => {
      const i = e.target.dataset.i; if (i == null) return;
      const f = e.target.dataset.f;
      if (f) { state.education[+i][f] = e.target.value; markDirty(); }
      if (e.target.classList.contains("edu-summary")) { state.education[+i].summary = e.target.value; markDirty(); }
    });
    $("#edu-list").addEventListener("click", (e) => {
      const btn = e.target.closest("[data-edu-act]"); if (!btn) return;
      const i = +btn.dataset.i, act = btn.dataset.eduAct;
      if (act === "up") state.education = move(state.education, i, i - 1);
      if (act === "down") state.education = move(state.education, i, i + 1);
      if (act === "del") {
        const name = state.education[i]?.school?.trim() || `教育经历第${i + 1}条`;
        if (!confirmDel(`教育经历「${name}」`)) return;
        state.education.splice(i, 1);
        if (!state.education.length) state.education.push(newEdu());
      }
      renderEdu(); markDirty();
    });

    // 模块
    $("#btn-add-section").addEventListener("click", () => {
      state.sections.push({ id: uid(), title: "新模块", enabled: true, items: [newItem()] });
      renderSections(); markDirty();
    });
    $("#section-list").addEventListener("input", (e) => {
      const t = e.target;
      if (t.classList.contains("sec-title")) { state.sections[+t.dataset.i].title = t.value; markDirty(); }
      if (t.dataset.if != null) { state.sections[+t.dataset.si].items[+t.dataset.i][t.dataset.if] = t.value; markDirty(); }
      if (t.classList.contains("item-bullets")) { state.sections[+t.dataset.si].items[+t.dataset.i].bullets = t.value; markDirty(); }
    });
    $("#section-list").addEventListener("change", (e) => {
      if (e.target.dataset.secShow != null) {
        state.sections[+e.target.dataset.secShow].enabled = e.target.checked;
        renderSections(); markDirty();
      }
    });
    $("#section-list").addEventListener("click", (e) => {
      const secBtn = e.target.closest("[data-sec-act]");
      if (secBtn) {
        const i = +secBtn.dataset.i, act = secBtn.dataset.secAct;
        if (act === "up") state.sections = move(state.sections, i, i - 1);
        if (act === "down") state.sections = move(state.sections, i, i + 1);
        if (act === "del") {
          const name = state.sections[i]?.title?.trim() || "未命名模块";
          if (!confirmDel(`模块「${name}」`)) return;
          state.sections.splice(i, 1);
        }
        renderSections(); markDirty(); return;
      }
      const itemBtn = e.target.closest("[data-item-act]");
      if (itemBtn) {
        const si = +itemBtn.dataset.si, i = +itemBtn.dataset.i, act = itemBtn.dataset.itemAct;
        const items = state.sections[si].items;
        if (act === "up") state.sections[si].items = move(items, i, i - 1);
        if (act === "down") state.sections[si].items = move(items, i, i + 1);
        if (act === "del") {
          if (items.length <= 1) return;
          const name = items[i]?.title?.trim() || `第${i + 1}条`;
          if (!confirmDel(`条目「${name}」`)) return;
          items.splice(i, 1);
        }
        renderSections(); markDirty(); return;
      }
      const add = e.target.closest(".item-add");
      if (add) { state.sections[+add.dataset.si].items.push(newItem()); renderSections(); markDirty(); }
    });

    // 技能
    $("#skills-show").addEventListener("change", (e) => { state.showSkills = e.target.checked; renderSkills(); markDirty(); });
    $("#skills-input").addEventListener("input", (e) => { state.skills = e.target.value; markDirty(); });

    // 版式
    $("#accent-preset").addEventListener("change", (e) => { state.config.layout.accentColor = e.target.value; $("#layout-accent").value = e.target.value; renderLayoutForm(); markDirty(); });
    $("#layout-accent").addEventListener("input", (e) => {
      state.config.layout.accentColor = e.target.value;
      $("#accent-preset").value = ACCENT_PRESETS.includes(e.target.value) ? e.target.value : ACCENT_PRESETS[0];
      markDirty();
    });
    $("#layout-font").addEventListener("change", (e) => { state.config.layout.fontFamily = e.target.value; markDirty(); });
    $("#layout-headerstyle").addEventListener("change", (e) => { state.config.layout.headerStyle = e.target.value; markDirty(); });
    $("#layout-margin").addEventListener("change", (e) => { state.config.layout.pageMarginMm = +e.target.value; markDirty(); });
    $("#layout-fontsize").addEventListener("input", (e) => { state.config.layout.bodyFontSizePt = +e.target.value; $("#fontsize-val").textContent = `${(+e.target.value).toFixed(1)} pt`; markDirty(); });
    $("#layout-lineheight").addEventListener("input", (e) => { state.config.layout.lineHeight = +e.target.value; $("#lineheight-val").textContent = (+e.target.value).toFixed(2); markDirty(); });

    // 文件列表
    $("#btn-new-file").addEventListener("click", newFile);
    $("#file-list").addEventListener("click", async (e) => {
      const op = e.target.closest(".file-op");
      const item = e.target.closest(".file-item");
      if (!item) return;
      const id = item.dataset.id;
      if (op) {
        const act = op.dataset.act;
        if (act === "open") await loadFile(id);
        if (act === "rename") await renameFile(id);
        if (act === "default") await setDefaultFile(id);
        if (act === "delete") await deleteFile(id);
        return;
      }
      if (id !== state.fileId) await loadFile(id);
    });

    // 润色弹窗
    $("#polish-close").addEventListener("click", () => $("#polish-modal").classList.add("hidden"));
    $("#polish-modal").addEventListener("click", (e) => { if (e.target === $("#polish-modal")) $("#polish-modal").classList.add("hidden"); });
    $("#polish-run").addEventListener("click", runPolish);
    $("#polish-targets").addEventListener("change", (e) => {
      const id = e.target.dataset.pt; if (!id) return;
      if (e.target.checked) state.polish.selected.push(id);
      else state.polish.selected = state.polish.selected.filter((x) => x !== id);
      renderPolishTargets();
    });
    $("#pc-select").addEventListener("change", (e) => { state.polish.activeId = e.target.value; renderCompare(); });
    $("#pc-back").addEventListener("click", () => { $("#polish-compare").classList.add("hidden"); });

    bindDrag();
  }


  /* ---------------- 模板选择 ---------------- */
  const TPL_THUMBS = {
    "modern-cn-001": '<div class="tpl-thumb thumb-cn"><div class="t-name"></div><div class="t-line w85" style="width:85%"></div><div class="t-sec"></div><div class="t-line" style="width:80%"></div><div class="t-line" style="width:65%"></div></div>',
    "modern-pro": '<div class="tpl-thumb thumb-pro"><div class="t-name"></div><div class="t-line w60"></div><div class="t-sec"></div><div class="t-line w85"></div><div class="t-line w60"></div></div>',
    "minimal-ink": '<div class="tpl-thumb thumb-min"><div class="t-name"></div><div class="t-dot"></div><div class="t-line"></div><div class="t-sec"></div><div class="t-line"></div></div>',
    "dual-column": '<div class="tpl-thumb thumb-dual"><div class="t-side"><i></i><i></i><i></i><i></i></div><div class="t-main"><div class="t-name"></div><div class="t-line" style="width:85%"></div><div class="t-sec"></div><div class="t-line" style="width:70%"></div></div></div>',
  };
  let templatesCache = [];
  async function loadTemplates() {
    try { templatesCache = await api("/templates"); } catch { templatesCache = []; }
    renderTplList();
  }
  function renderTplList() {
    const wrap = $("#tpl-list");
    if (!wrap) return;
    const list = templatesCache.length ? templatesCache : [{ id: state.config.templateId, name: "当前模板" }];
    wrap.innerHTML = list.map((t) => `
      <div class="tpl-card ${t.id === state.config.templateId ? "active" : ""}" data-tpl="${t.id}" title="${esc(t.description || t.name)}">
        ${TPL_THUMBS[t.id] || '<div class="tpl-thumb"></div>'}
        <div class="tpl-name">${esc(t.name)}</div>
      </div>`).join("");
  }
  function bindTplPicker() {
    const wrap = $("#tpl-list");
    if (!wrap) return;
    wrap.addEventListener("click", (e) => {
      const card = e.target.closest(".tpl-card");
      if (!card) return;
      state.config.templateId = card.dataset.tpl;
      renderTplList();
      markDirty();
    });
  }

  /* ---------------- 启动 ---------------- */
  async function init() {
    bind();
    bindTplPicker();
    void loadTemplates();
    try {
      const pick = await loadFiles();
      if (pick) await loadFile(pick);
      else setStatus("暂无简历文件", "err");
    } catch (e) {
      setStatus(`加载失败：${e.message}`, "err");
    }
  }
  document.addEventListener("DOMContentLoaded", init);
})();
