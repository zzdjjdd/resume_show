/* ============================================================
   AI 一键生成简历 · 对话式交互逻辑
   与后端 /resume/ai-chat 交互；生成后实时渲染并可保存/导出。
   ============================================================ */
(() => {
  "use strict";
  const API = "";
  const $ = (s) => document.querySelector(s);

  const state = {
    messages: [],          // [{role:'user'|'assistant', content}]
    resume: null,          // 生成出的简历 JSON
    designs: [],           // AI 自定义排版 [{name, desc, html}]
    designIdx: 0,
    fallbackTpl: "modern-pro",  // AI 排版失败时的兜底模板
    busy: false,
  };

  const esc = (s) => String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");

  async function post(path, body) {
    const r = await fetch(`${API}${path}`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const text = await r.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch { data = { detail: text }; }
    if (!r.ok) throw new Error((data && data.detail) || `请求失败（${r.status}）`);
    return data;
  }

  // ---- 消息渲染 ----
  function addMsg(role, content, opts) {
    opts = opts || {};
    const list = $("#chat-list");
    const wrap = document.createElement("div");
    wrap.className = "msg " + (role === "user" ? "user" : "ai");
    const avatar = role === "user" ? "🙂" : "✨";
    wrap.innerHTML =
      `<div class="msg-avatar">${avatar}</div><div class="msg-bubble"></div>`;
    const bubble = wrap.querySelector(".msg-bubble");
    // AI 回复中的 <think> 块渲染为可折叠“思考过程”
    if (window.HudRender && role !== "user") window.HudRender.message(bubble, content);
    else bubble.textContent = content;
    list.appendChild(wrap);
    scrollBottom();
    return wrap;
  }
  function addTyping() {
    const list = $("#chat-list");
    const wrap = document.createElement("div");
    wrap.className = "msg ai typing";
    wrap.id = "typing-msg";
    wrap.innerHTML =
      `<div class="msg-avatar">✨</div><div class="msg-bubble">` +
      `<span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span></div>`;
    list.appendChild(wrap);
    scrollBottom();
  }
  function removeTyping() {
    const t = $("#typing-msg");
    if (t) t.remove();
  }
  function scrollBottom() {
    const sc = $("#chat-scroll");
    sc.scrollTop = sc.scrollHeight;
  }

  function setBusy(b) {
    state.busy = b;
    $("#btn-generate").disabled = b;
    $("#btn-send").disabled = b;
    $("#chat-input").disabled = b;
  }
  function setStatus(text, cls) {
    const el = $("#pv-status");
    el.textContent = text || "";
    el.className = "aic-pv-status" + (cls ? " " + cls : "");
  }

  // ---- 一键生成进度条（两段式伪进度：等待期也持续慢爬 + 计时，绝不视觉卡死） ----
  const prog = { timer: null, value: 0, cap: 99, startedAt: 0 };
  function elapsedSec() { return Math.floor((Date.now() - prog.startedAt) / 1000); }
  function renderProgress() {
    $("#gen-prog-fill").style.width = prog.value.toFixed(1) + "%";
    $("#gen-prog-pct").textContent = Math.floor(prog.value) + "%";
  }
  function renderElapsed() {
    const el = document.getElementById("gen-prog-elapsed");
    if (el) el.textContent = "已用时 " + elapsedSec() + "s";
  }
  function startProgress(stage) {
    prog.value = 6;
    prog.startedAt = Date.now();
    $("#gen-prog-stage").textContent = stage || "准备中…";
    renderProgress();
    renderElapsed();
    $("#gen-progress").classList.remove("hidden");
    clearInterval(prog.timer);
    prog.timer = setInterval(() => {
      // 两段式：50% 之前较快；之后（AI 排版等待期）极慢爬行直到 99%
      const step = prog.value < 50
        ? Math.max(0.2, (prog.cap - prog.value) * 0.03)
        : Math.max(0.02, (prog.cap - prog.value) * 0.004);
      prog.value = Math.min(prog.cap, prog.value + step);
      renderProgress();
      renderElapsed();
    }, 220);
  }
  function setProgressStage(stage, base) {
    if (base != null && base > prog.value) prog.value = base;
    $("#gen-prog-stage").textContent = stage;
    renderProgress();
  }
  function finishProgress() {
    clearInterval(prog.timer); prog.timer = null;
    prog.value = 100; renderProgress();
    $("#gen-prog-stage").textContent = "完成！正在打开预览…";
    setTimeout(() => $("#gen-progress").classList.add("hidden"), 600);
  }
  function abortProgress() {
    clearInterval(prog.timer); prog.timer = null;
    $("#gen-progress").classList.add("hidden");
  }

  // ---- 预览（弹窗固定窗口：尺寸不随内容变化，超长在 iframe 内滚动） ----
  /* 注入宽度约束：AI 排版内容固定适配预览窗宽，居中显示，杜绝横向撑开/横向滚动条 */
  const PV_FIX_STYLE =
    "<style id='pv-fix'>html,body{max-width:100% !important;width:100% !important;" +
    "overflow-x:hidden !important}body>*{max-width:100%}body{margin-left:auto !important;" +
    "margin-right:auto !important}</style>";
  function writePreviewDoc(frame, html) {
    const fixed = html.includes("</head>")
      ? html.replace("</head>", PV_FIX_STYLE + "</head>")
      : html + PV_FIX_STYLE;
    const doc = frame.contentDocument;
    doc.open(); doc.write(fixed); doc.close();
  }

  function renderPreview() {
    if (!state.resume || !state.designs.length) return;
    const v = state.designs[state.designIdx];
    const frame = $("#pv-frame");
    writePreviewDoc(frame, v.html);
    $("#btn-save-file").disabled = false;
    $("#btn-pdf").disabled = false;
  }

  /* 兜底预览：AI 排版失败时用内置模板渲染，保证弹窗不空白 */
  async function renderFallbackPreview() {
    if (!state.resume) return;
    try {
      const r = await fetch(`${API}/export/html`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ resume: state.resume, templateId: state.fallbackTpl }),
      });
      if (!r.ok) return;
      const html = await r.text();
      writePreviewDoc($("#pv-frame"), html);
      $("#btn-save-file").disabled = false;
      $("#btn-pdf").disabled = false;
    } catch (e) { /* ignore */ }
  }

  /* 弹窗内加载中占位 */
  function showPreviewLoading(text) {
    const frame = $("#pv-frame");
    frame.style.height = "72vh";
    const doc = frame.contentDocument;
    doc.open();
    doc.write(
      "<!doctype html><html><head><meta charset='utf-8'><style>" +
      "html,body{height:100%;margin:0}" +
      "body{display:flex;flex-direction:column;align-items:center;justify-content:center;" +
      "gap:14px;font-family:'PingFang SC','Microsoft YaHei',sans-serif;color:#64748b;background:#fff}" +
      ".s{width:42px;height:42px;border-radius:50%;border:3px solid #e2e8f0;border-top-color:#6366f1;" +
      "animation:r 1s linear infinite}@keyframes r{to{transform:rotate(360deg)}}" +
      "p{font-size:14px;margin:0}</style></head><body><div class='s'></div>" +
      `<p>${text}</p></body></html>`
    );
    doc.close();
  }

  /* 调 AI 设计排版：先出一版立即预览（提速），另一版后台静默补充 */
  async function fetchDesign(direction) {
    const data = await post("/resume/ai-design", window.LLMSettings.inject({
      resume: state.resume, direction,
    }));
    if (!data.versions || !data.versions.length) throw new Error("未获得排版版本");
    return data.versions;
  }

  async function genDesigns() {
    setStatus("AI 正在设计精美排版，请稍候…");
    showPreviewLoading("AI 正在为你设计精美排版…");
    try {
      // 第一版：快速预览，完成即关进度条
      state.designs = await fetchDesign(0);
      state.designIdx = 0;
      renderDesignChips();
      renderPreview();
      setStatus("已生成第 1 版排版，第 2 版正在后台生成中…", "ok");
      finishProgress();
      // 第二版：后台补充，失败不影响已有一版
      try {
        const second = await fetchDesign(1);
        state.designs = state.designs.concat(second);
        renderDesignChips();
        setStatus(`已生成 ${state.designs.length} 版排版，选一版或点「重新生成」`, "ok");
      } catch (e2) {
        setStatus("第 2 版生成失败（可点「重新生成」重试），当前版可正常使用", "");
      }
    } catch (e) {
      // 兜底：用内置模板渲染，弹窗绝不空白；可点「重新生成」重试 AI 排版
      await renderFallbackPreview();
      setStatus("AI 排版失败（" + e.message + "），已先用内置模板预览，可点「重新生成」重试", "err");
      throw e;
    }
  }

  function openPreview() {
    if (!state.resume) {
      setStatus("先描述背景并点击「一键生成简历」，再预览", "err");
      return;
    }
    $("#preview-modal").classList.remove("hidden");
    if (state.designs.length) {
      renderPreview();
    } else {
      showPreviewLoading("正在准备预览…");
    }
  }
  function closePreview() { $("#preview-modal").classList.add("hidden"); }

  function renderDesignChips() {
    const wrap = $("#tpl-chips");
    wrap.innerHTML = state.designs.map((v, i) =>
      `<button class="tpl-mini ${i === state.designIdx ? "active" : ""}" data-idx="${i}" type="button" title="${esc(v.desc || "")}">${esc(v.name)}</button>`
    ).join("");
  }

  // ---- 对话 ----
  async function sendChat(wantGenerate) {
    const input = $("#chat-input");
    const text = input.value.trim();
    if (!text && !wantGenerate) return;
    if (state.busy) return;
    if (wantGenerate && !window.LLMSettings.hasConfig()) {
      addMsg("ai", "⚠️ 请先在右上角「大模型设置」中配置 Base URL 与 API Key，再一键生成。");
      window.LLMSettings.open();
      return;
    }

    if (text) {
      state.messages.push({ role: "user", content: text });
      addMsg("user", text);
      input.value = "";
      $("#quick-wrap").classList.add("hidden");
    }
    if (!state.messages.length) return;

    setBusy(true);
    setStatus("");
    if (wantGenerate) startProgress("AI 正在分析对话，整理你的背景信息…");
    addTyping();
    try {
      const body = window.LLMSettings.inject({
        messages: state.messages,
        wantGenerate: !!wantGenerate,
      });
      const data = await post("/resume/ai-chat", body);
      removeTyping();
      if (data.type === "resume" && data.resume) {
        state.resume = data.resume;
        const reply = data.reply || "已生成简历。";
        // 历史上下文去掉 think 块，保持干净
        state.messages.push({ role: "assistant", content: reply.replace(/<think>[\s\S]*?<\/think>/gi, "").trim() || reply });
        addMsg("ai", reply + "\n\n✅ 简历已生成，**AI 正在直接设计精美排版**（不再使用固定模板），第一版完成后立即预览，第二版后台自动补充，不满意可重新生成。");
        setProgressStage("简历生成成功 · AI 正在设计精美排版…", 52);
        openPreview();
        try { await genDesigns(); } catch (e) { /* 状态栏已提示；失败时也要收掉进度条 */ finishProgress(); }
      } else {
        if (wantGenerate) abortProgress();
        const reply = data.reply || "请继续补充信息。";
        state.messages.push({ role: "assistant", content: reply.replace(/<think>[\s\S]*?<\/think>/gi, "").trim() || reply });
        addMsg("ai", reply);
      }
    } catch (e) {
      removeTyping();
      abortProgress();
      addMsg("ai", "⚠️ " + e.message);
      setStatus(e.message, "err");
    } finally {
      setBusy(false);
    }
  }

  // ---- 保存 / 导出 ----
  async function saveAsFile() {
    if (!state.resume) return;
    try {
      const name = (state.resume.basics && state.resume.basics.name) || "AI 生成简历";
      const ver = state.designs[state.designIdx];
      const rec = await post("/resume-files", {
        name: `${name} · AI 生成`,
        resume: state.resume,
        config: { aiDesignName: ver ? ver.name : null },
      });
      setStatus(`已存为档案「${rec.name}」，可前往编辑器继续修改`, "ok");
    } catch (e) {
      setStatus("保存失败：" + e.message, "err");
    }
  }
  async function exportPdf() {
    if (!state.resume) return;
    const ver = state.designs[state.designIdx];
    setStatus("正在导出 PDF…");
    try {
      let r;
      if (ver) {
        r = await fetch(`${API}/export/pdf-html`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ html: ver.html }),
        });
      } else {
        // 兜底：没有 AI 排版时用内置模板导出
        r = await fetch(`${API}/export/pdf`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ resume: state.resume, templateId: state.fallbackTpl }),
        });
      }
      if (!r.ok) {
        let msg = `导出失败（${r.status}）`;
        try { msg = (await r.json()).detail || msg; } catch { /* ignore */ }
        throw new Error(msg);
      }
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${(state.resume.basics && state.resume.basics.name) || "resume"}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      setStatus("PDF 已导出", "ok");
    } catch (e) {
      setStatus(e.message, "err");
    }
  }

  // ---- 初始化 ----
  function bind() {
    $("#btn-send").addEventListener("click", () => sendChat(false));
    $("#btn-generate").addEventListener("click", () => sendChat(true));
    $("#btn-settings").addEventListener("click", () => window.LLMSettings.open());
    $("#btn-preview").addEventListener("click", openPreview);
    $("#pv-close").addEventListener("click", closePreview);
    $("#preview-modal").addEventListener("click", (e) => {
      if (e.target === $("#preview-modal")) closePreview();
    });
    $("#btn-redesign").addEventListener("click", async () => {
      if (!state.resume || state.busy) return;
      try { await genDesigns(); } catch (e) { /* 状态栏已提示 */ }
    });
    $("#btn-save-file").addEventListener("click", saveAsFile);
    $("#btn-pdf").addEventListener("click", exportPdf);
    $("#chat-input").addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); sendChat(true); }
    });
    $("#tpl-chips").addEventListener("click", (e) => {
      const b = e.target.closest(".tpl-mini");
      if (!b) return;
      state.designIdx = Number(b.dataset.idx) || 0;
      renderDesignChips();
      renderPreview();
    });
    document.querySelectorAll(".aic-chip").forEach((c) => {
      c.addEventListener("click", () => {
        $("#chat-input").value = c.dataset.fill || "";
        $("#chat-input").focus();
      });
    });
  }

  function init() {
    bind();
    addMsg("ai",
      "你好，我是你的 AI 简历顾问 ✨\n\n告诉我你的背景（教育、工作/项目经历、技能、求职目标），" +
      "我会帮你整理成一份专业简历，并**直接设计两版精美排版**供你挑选。\n\n你可以直接点「一键生成简历」，也可以先点「发送」让我追问补充细节。");
  }
  document.addEventListener("DOMContentLoaded", init);
})();
