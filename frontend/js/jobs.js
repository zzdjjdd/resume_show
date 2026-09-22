/* ============================================================
   岗位雷达 · jobs.js
   岗位列表 / 筛选排序 / 简历匹配度 / 详情弹窗
   所有动态文本经 esc() 转义，防 XSS
   ============================================================ */
(function () {
  "use strict";

  function $(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  var state = {
    jobs: [], cities: [], categories: [],
    files: [],
    keyword: "", city: "", category: "",
    sort: "publish",
    matchOn: true,
    scores: {},          // jobId -> score
    breakdown: {},       // jobId -> 完整 match 对象
    resumeId: "",
    resume: null,
    resumeText: "",      // PDF 解析出的纯文本简历
    pdfName: "",
    loading: true
  };

  function hasResume() { return !!(state.resumeId || state.resumeText); }

  /* 构造匹配请求体：PDF 文本优先，其次结构化档案 */
  function matchBody(extra) {
    var body = {};
    if (state.resumeText) body.resumeText = state.resumeText;
    else if (state.resume) body.resume = state.resume;
    if (extra) Object.keys(extra).forEach(function (k) { body[k] = extra[k]; });
    return body;
  }

  /* ---------------- 数据加载 ---------------- */

  async function fetchJobs() {
    try {
      var res = await fetch("/jobs");
      var data = await res.json();
      state.jobs = data.jobs || [];
      state.cities = data.cities || [];
      state.categories = data.categories || [];
    } catch (e) {
      state.jobs = [];
    }
  }

  async function fetchFiles() {
    try {
      var res = await fetch("/resume-files");
      state.files = (await res.json()) || [];
    } catch (e) {
      state.files = [];
    }
    renderFileSelect();
  }

  function renderFileSelect() {
    var sel = $("resume-select");
    var html = '<option value="">—— 未选择简历 ——</option>';
    state.files.forEach(function (f) {
      html += '<option value="' + esc(f.id) + '">' + esc(f.name || f.id) +
        (f.isDefault ? " ★" : "") + "</option>";
    });
    sel.innerHTML = html;
    var def = state.files.find(function (f) { return f.isDefault; }) || state.files[0];
    if (def) {
      sel.value = def.id;
      onResumeChange();
    }
  }

  /* ---------------- 匹配计算 ---------------- */

  function setStatus(kind, text) {
    var box = $("match-status");
    box.classList.remove("scanning", "done");
    if (kind) box.classList.add(kind);
    $("match-status-text").textContent = text;
  }

  async function onResumeChange() {
    state.resumeId = $("resume-select").value;
    state.resume = null;
    state.scores = {};
    state.breakdown = {};
    // 选档案时清除 PDF 来源
    if (state.resumeId) clearPdfSource(false);
    if (!hasResume() || !state.matchOn) {
      setStatus("", "STANDBY · 待命");
      render();
      return;
    }
    setStatus("scanning", "SCANNING · 匹配计算中…");
    try {
      if (state.resumeId) {
        var res = await fetch("/resume-files/" + encodeURIComponent(state.resumeId));
        var data = await res.json();
        state.resume = data.resume || data || {};
      }
      var m = await fetch("/jobs/match", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(matchBody())
      });
      var body = await m.json();
      (body.matches || []).forEach(function (it) { state.scores[it.jobId] = it.score; });
      if (body.note) {
        setStatus("", "WARN · " + body.note);
      } else {
        setStatus("done", "LOCKED · 匹配完成 · " + Object.keys(state.scores).length + " 岗位");
        if (state.sort !== "salary") setSort("match");
      }
    } catch (e) {
      setStatus("", "ERROR · 匹配计算失败");
    }
    render();
  }

  /* ---------------- PDF 简历上传 ---------------- */

  function clearPdfSource(rerender) {
    state.resumeText = "";
    state.pdfName = "";
    var badge = $("jobs-pdf-badge");
    badge.classList.add("hidden");
    badge.textContent = "";
    if (rerender !== false) onResumeChange();
  }

  async function onPdfPicked(file) {
    if (!file) return;
    setStatus("scanning", "PARSING · 正在解析 PDF…");
    try {
      var fd = new FormData();
      fd.append("file", file);
      if (window.LLMSettings) {
        var c = window.LLMSettings.get();
        if (c.baseUrl) fd.append("baseUrl", c.baseUrl);
        if (c.apiKey) fd.append("apiKey", c.apiKey);
        if (c.model) fd.append("model", c.model);
      }
      var r = await fetch("/interview/parse-pdf", { method: "POST", body: fd });
      var data = await r.json();
      if (!r.ok) throw new Error(data.detail || ("解析失败（" + r.status + "）"));
      state.resumeText = data.text;
      state.pdfName = file.name;
      // 切换为 PDF 来源：取消档案选中
      state.resumeId = "";
      state.resume = null;
      $("resume-select").value = "";
      var badge = $("jobs-pdf-badge");
      badge.textContent = "📄 " + file.name + " · " + (data.method === "ocr" ? "AI OCR" : "已解析") + " ✕";
      badge.classList.remove("hidden");
      await onResumeChange();
    } catch (e) {
      setStatus("", "ERROR · " + e.message);
    }
  }

  /* ---------------- 筛选与排序（本地） ---------------- */

  function visibleJobs() {
    var kw = state.keyword.trim().toLowerCase();
    var list = state.jobs.filter(function (j) {
      if (state.city && j.city !== state.city) return false;
      if (state.category && j.category !== state.category) return false;
      if (kw) {
        var hay = ([j.title, j.company, j.category, j.city, j.description]
          .concat(j.skills || []).concat(j.tags || [])).join("|").toLowerCase();
        if (hay.indexOf(kw) === -1) return false;
      }
      return true;
    });
    var hasScore = state.matchOn && hasResume();
    list.sort(function (a, b) {
      if (state.sort === "salary") return (b.salaryMax - a.salaryMax) || (b.salaryMin - a.salaryMin);
      if (state.sort === "match" && hasScore) return (state.scores[b.id] || 0) - (state.scores[a.id] || 0);
      return String(b.publishDate || "").localeCompare(String(a.publishDate || ""));
    });
    return list;
  }

  function setSort(v) {
    state.sort = v;
    $("f-sort").value = v;
  }

  /* ---------------- 渲染 ---------------- */

  function tierOf(score) {
    if (score >= 80) return "jr-tier-high";
    if (score >= 60) return "jr-tier-mid";
    return "jr-tier-low";
  }
  function tierText(score) {
    if (score >= 80) return "高度匹配";
    if (score >= 60) return "较匹配";
    return "待提升";
  }

  function ringHtml(score) {
    var C = 2 * Math.PI * 24; // r=24
    var off = C * (1 - Math.max(0, Math.min(100, score)) / 100);
    return '<div class="jr-ring">' +
      '<svg width="58" height="58" viewBox="0 0 58 58">' +
      '<circle class="jr-ring-bg" cx="29" cy="29" r="24"/>' +
      '<circle class="jr-ring-val" cx="29" cy="29" r="24" stroke-dasharray="' + C.toFixed(1) +
      '" stroke-dashoffset="' + off.toFixed(1) + '"/></svg>' +
      '<span class="jr-ring-num">' + score + "</span></div>";
  }

  function cardHtml(j, idx) {
    var hasScore = state.matchOn && hasResume();
    var score = state.scores[j.id];
    var tier = hasScore ? tierOf(score || 0) : "";
    var salary = esc(j.salaryMin) + "-" + esc(j.salaryMax) + "K";
    var html = '<article class="jr-card ' + tier + '" data-id="' + esc(j.id) + '" style="animation-delay:' + Math.min(idx * 0.05, 0.5) + 's">';
    html += '<div class="jr-card-top"><div class="jr-card-head">';
    html += '<h3 class="jr-title">' + esc(j.title) + "</h3>";
    html += '<div class="jr-company">' + esc(j.company) + ' <span class="jr-city-dot"></span> ' +
      esc(j.city) + " · " + esc(j.category) + "</div></div>";
    if (hasScore) html += ringHtml(score || 0);
    html += "</div>";
    html += '<div class="jr-salary">' + salary + '<span class="jr-salary-note">月薪</span></div>';
    html += '<div class="jr-tags">' +
      '<span class="jr-tag">' + esc(j.experience) + "</span>" +
      '<span class="jr-tag">' + esc(j.education) + "</span>" +
      (j.tags || []).slice(0, 3).map(function (t) { return '<span class="jr-tag warm">' + esc(t) + "</span>"; }).join("") +
      "</div>";
    html += '<div class="jr-tags">' +
      (j.skills || []).slice(0, 6).map(function (s) { return '<span class="jr-tag dim">' + esc(s) + "</span>"; }).join("") +
      "</div>";
    if ((j.benefits || []).length) {
      html += '<div class="jr-benefits">' +
        j.benefits.map(function (b) { return '<span class="jr-benefit">' + esc(b) + "</span>"; }).join("") +
        "</div>";
    }
    if (hasScore) {
      html += '<div class="jr-card-foot">' +
        '<div class="jr-match-line"><span class="jr-match-label">MATCH · 匹配度</span>' +
        '<span class="jr-match-tier">' + tierText(score || 0) + "</span></div>" +
        '<div class="jr-bar"><div class="jr-bar-fill" data-w="' + (score || 0) + '"></div></div></div>';
    }
    html += '<div class="jr-card-date"><span>发布 ' + esc(j.publishDate || "—") + "</span>" +
      '<span class="jr-view-jd">查看 JD 与匹配分解 →</span></div>';
    html += "</article>";
    return html;
  }

  function renderChips() {
    var wrap = $("f-cities");
    wrap.innerHTML = chip("city", "", "全部") + state.cities.map(function (c) { return chip("city", c, c); }).join("");
    var wrap2 = $("f-categories");
    wrap2.innerHTML = chip("category", "", "全部") + state.categories.map(function (c) { return chip("category", c, c); }).join("");
  }
  function chip(group, val, label) {
    var active = state[group] === val ? " active" : "";
    return '<button type="button" class="jr-chip' + active + '" data-group="' + group + '" data-val="' + esc(val) + '">' + esc(label) + "</button>";
  }

  function countUp(el, target, suffixHtml) {
    var start = parseInt(el.getAttribute("data-count") || "0", 10) || 0;
    var t0 = performance.now(), dur = 750;
    function step(t) {
      var p = Math.min(1, (t - t0) / dur);
      var eased = 1 - Math.pow(1 - p, 3);
      var v = Math.round(start + (target - start) * eased);
      el.innerHTML = v + (suffixHtml || "");
      if (p < 1) requestAnimationFrame(step);
      else el.setAttribute("data-count", String(target));
    }
    requestAnimationFrame(step);
  }

  function renderStats(visible) {
    var total = state.jobs.length;
    var avg = 0;
    if (total) {
      var sum = state.jobs.reduce(function (s, j) { return s + (j.salaryMin + j.salaryMax) / 2; }, 0);
      avg = Math.round(sum / total);
    }
    var best = null;
    if (state.matchOn && hasResume()) {
      Object.keys(state.scores).forEach(function (k) {
        if (best === null || state.scores[k] > best) best = state.scores[k];
      });
    }
    countUp($("stat-total"), total);
    countUp($("stat-salary"), avg, '<span class="jr-stat-unit">K</span>');
    countUp($("stat-cities"), state.cities.length);
    var bestEl = $("stat-best");
    if (best === null) {
      bestEl.textContent = "—";
      bestEl.setAttribute("data-count", "0");
    } else {
      countUp(bestEl, best, '<span class="jr-stat-unit">%</span>');
    }
  }

  function render() {
    var list = visibleJobs();
    var listEl = $("jobs-list");
    $("jobs-loading").classList.toggle("hidden", !state.loading);
    $("jobs-empty").classList.toggle("hidden", state.loading || list.length > 0);
    listEl.innerHTML = list.map(cardHtml).join("");
    // 进度条渐入动画
    requestAnimationFrame(function () {
      listEl.querySelectorAll(".jr-bar-fill").forEach(function (b) {
        requestAnimationFrame(function () { b.style.width = (b.getAttribute("data-w") || "0") + "%"; });
      });
    });
    renderStats(list);
  }

  /* ---------------- 详情弹窗 ---------------- */

  async function openModal(jobId) {
    var job = state.jobs.find(function (j) { return j.id === jobId; });
    if (!job) return;
    var modal = $("job-modal");
    $("job-modal-code").textContent = job.id;
    $("job-modal-name").textContent = job.title;
    $("job-modal-body").innerHTML = '<div class="jd-noresume">载入中…</div>';
    modal.classList.remove("hidden");

    var match = null;
    if (state.matchOn && hasResume()) {
      if (state.breakdown[jobId]) {
        match = state.breakdown[jobId];
      } else {
        try {
          var res = await fetch("/jobs/match", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(matchBody({ jobId: jobId }))
          });
          var data = await res.json();
          if (data && data.match) {
            match = data.match;
            state.breakdown[jobId] = match;
          }
        } catch (e) { /* 静默：仅展示 JD */ }
      }
    }
    renderModal(job, match);
  }

  function barRow(label, pct) {
    return '<div class="jd-bd-row"><span class="jd-bd-label">' + esc(label) + '</span>' +
      '<div class="jd-bd-bar"><div class="jd-bd-fill" data-w="' + pct + '"></div></div>' +
      '<span class="jd-bd-num">' + pct + "%</span></div>";
  }

  /* 把【岗位职责】【任职要求】等结构化 JD 渲染为分节列表 */
  function descHtml(desc) {
    var text = String(desc || "");
    if (!text.trim()) return '<div class="jd-desc">暂无详细描述</div>';
    var parts = text.split(/【([^】]{2,12})】/);
    // 无分节标记：直接保留换行展示
    if (parts.length < 3) {
      return '<div class="jd-desc">' + esc(text) + "</div>";
    }
    var html = "";
    if (parts[0].trim()) html += '<div class="jd-desc">' + esc(parts[0].trim()) + "</div>";
    for (var i = 1; i + 1 < parts.length; i += 2) {
      var title = parts[i].trim();
      var body = parts[i + 1].trim();
      html += '<div class="jd-block"><div class="jd-block-title">' + esc(title) + "</div>";
      var lines = body.split("\n").map(function (l) { return l.trim(); }).filter(Boolean);
      html += '<ul class="jd-block-list">' + lines.map(function (l) {
        return "<li>" + esc(l.replace(/^\d+[.、)]\s*/, "")) + "</li>";
      }).join("") + "</ul></div>";
    }
    return html;
  }

  function renderModal(job, match) {
    var html = '<div class="jd-meta">' +
      '<span class="jr-tag">' + esc(job.city) + "</span>" +
      '<span class="jr-tag">' + esc(job.category) + "</span>" +
      '<span class="jr-tag dim">' + esc(job.experience) + "</span>" +
      '<span class="jr-tag dim">' + esc(job.education) + "</span>" +
      (job.tags || []).map(function (t) { return '<span class="jr-tag warm">' + esc(t) + "</span>"; }).join("") +
      "</div>";
    html += '<div class="jd-salary">' + esc(job.salaryMin) + "-" + esc(job.salaryMax) + "K<span" +
      ' class="jr-salary-note">月薪</span></div>';

    html += '<div class="jd-section-title">职位描述 · JOB DESCRIPTION</div>';
    html += descHtml(job.description);

    if (match) {
      var skillPct = (job.skills || []).length
        ? Math.round(match.skillsMatched.length / job.skills.length * 100) : 100;
      html += '<div class="jd-section-title">技能对照 · SKILL MATRIX（命中 ' +
        match.skillsMatched.length + " / " + job.skills.length + "）</div>";
      html += '<div class="jd-skills">';
      (match.skillsMatched || []).forEach(function (s) { html += '<span class="jd-skill hit">' + esc(s) + "</span>"; });
      (match.skillsMissing || []).forEach(function (s) { html += '<span class="jd-skill miss">' + esc(s) + "</span>"; });
      html += "</div>";

      html += '<div class="jd-section-title">匹配分解 · MATCH BREAKDOWN（总分 ' + esc(match.score) + "）</div>";
      html += '<div class="jd-breakdown">' +
        barRow("技能匹配 · 50%", skillPct) +
        barRow("经验匹配 · 30%", match.expScore) +
        barRow("学历匹配 · 20%", match.eduScore) +
        "</div>";
      html += '<div class="jd-summary"><b>雷达结论：</b>' + esc(match.summary) + "</div>";
    } else {
      html += '<div class="jd-noresume">未选择简历或匹配开关已关闭 —— 选择档案 / 上传简历 PDF 并开启「计算匹配度」后可查看技能对照与匹配分解。</div>';
    }
    $("job-modal-body").innerHTML = html;
    requestAnimationFrame(function () {
      $("job-modal-body").querySelectorAll(".jd-bd-fill").forEach(function (b) {
        requestAnimationFrame(function () { b.style.width = (b.getAttribute("data-w") || "0") + "%"; });
      });
    });
  }

  function closeModal() { $("job-modal").classList.add("hidden"); }

  /* ---------------- 事件绑定 ---------------- */

  function debounce(fn, ms) {
    var t; return function () { clearTimeout(t); var a = arguments, c = this; t = setTimeout(function () { fn.apply(c, a); }, ms); };
  }

  function init() {
    $("btn-settings").addEventListener("click", function () {
      if (window.LLMSettings) window.LLMSettings.open();
    });

    var kwTimer;
    $("f-keyword").addEventListener("input", debounce(function (e) {
      state.keyword = e.target.value;
      render();
    }, 220));

    $("f-sort").addEventListener("change", function (e) {
      state.sort = e.target.value;
      render();
    });

    document.addEventListener("click", function (e) {
      var chipEl = e.target.closest ? e.target.closest(".jr-chip") : null;
      if (chipEl) {
        var g = chipEl.getAttribute("data-group");
        state[g] = chipEl.getAttribute("data-val");
        renderChips();
        render();
        return;
      }
      var card = e.target.closest ? e.target.closest(".jr-card") : null;
      if (card) { openModal(card.getAttribute("data-id")); return; }
    });

    $("match-toggle").addEventListener("change", function (e) {
      state.matchOn = e.target.checked;
      if (state.matchOn && hasResume()) { onResumeChange(); }
      else { state.scores = {}; state.breakdown = {}; setStatus("", "STANDBY · 待命"); render(); }
    });

    $("resume-select").addEventListener("change", onResumeChange);

    // PDF 上传
    $("btn-jobs-pdf").addEventListener("click", function () { $("jobs-pdf-input").click(); });
    $("jobs-pdf-input").addEventListener("change", function (e) {
      var f = e.target.files && e.target.files[0];
      if (f) onPdfPicked(f);
      e.target.value = "";
    });
    $("jobs-pdf-badge").addEventListener("click", function () { clearPdfSource(); });

    $("btn-reset-filter").addEventListener("click", function () {
      state.keyword = ""; state.city = ""; state.category = "";
      $("f-keyword").value = "";
      renderChips(); render();
    });

    $("job-modal-x").addEventListener("click", closeModal);
    $("job-modal").addEventListener("click", function (e) { if (e.target === this) closeModal(); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeModal(); });

    bootstrap();
  }

  async function bootstrap() {
    await Promise.all([fetchJobs(), fetchFiles()]);
    state.loading = false;
    renderChips();
    render();
    if (!state.resumeId) setStatus("", "STANDBY · 待命");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
