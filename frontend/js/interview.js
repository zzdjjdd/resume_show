/* ============================================================
   AI 模拟面试 · 对话式交互逻辑
   面试官（AI）基于简历提问 → 候选人作答 → AI 点评并追问。
   使用 window.LLMSettings.inject(body) 注入大模型配置。
   ============================================================ */
(() => {
  "use strict";
  const API = "";
  const $ = (s) => document.querySelector(s);

  const state = {
    files: [],
    fileId: null,
    source: "file",        // 'file'（档案） | 'pdf'（导入 PDF）
    pdfText: "",
    pdfName: "",
    started: false,
    ended: false,
    busy: false,
    turns: 0,
    messages: [], // [{role:'user'|'assistant', content}] 候选人=user，面试官=assistant
  };

  const esc = (s) => String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");

  function cfgStatus(text, cls) {
    const el = $("#iv-config-status");
    el.textContent = text || "";
    el.className = "iv-config-status" + (cls ? " " + cls : "");
  }
  function setBusy(b) {
    state.busy = b;
    $("#btn-send").disabled = b || !state.started || state.ended;
    $("#chat-input").disabled = b || !state.started || state.ended;
    $("#btn-start").disabled = b || state.started;
  }
  function scrollBottom() {
    const sc = $("#chat-scroll");
    sc.scrollTop = sc.scrollHeight;
  }
  function updateTurn() {
    $("#turn-counter").textContent = state.started ? `已进行 ${state.turns} 轮问答` : "";
  }

  function addMsg(role, content) {
    const list = $("#chat-list");
    const wrap = document.createElement("div");
    const isUser = role === "user";
    wrap.className = "msg " + (isUser ? "user iv-user" : "ai iv-ai");
    const avatar = isUser ? "🙂" : "🎙️";
    wrap.innerHTML = `<div class="msg-avatar">${avatar}</div><div class="msg-bubble"></div>`;
    const bubble = wrap.querySelector(".msg-bubble");
    // 面试官回复中的 <think> 块渲染为可折叠“思考过程”
    if (window.HudRender && !isUser) window.HudRender.message(bubble, content);
    else bubble.textContent = content;
    list.appendChild(wrap);
    scrollBottom();
    return wrap;
  }
  // 历史上下文去掉 think 块，保持干净
  function cleanReply(reply) {
    const c = String(reply || "").replace(/<think>[\s\S]*?<\/think>/gi, "").trim();
    return c || String(reply || "");
  }
  function addTyping() {
    const list = $("#chat-list");
    const wrap = document.createElement("div");
    wrap.className = "msg ai iv-ai typing";
    wrap.id = "iv-typing";
    wrap.innerHTML = `<div class="msg-avatar">🎙️</div><div class="msg-bubble">` +
      `<span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span></div>`;
    list.appendChild(wrap);
    scrollBottom();
  }
  function removeTyping() {
    const t = $("#iv-typing");
    if (t) t.remove();
  }

  function buildBody(extraMessages) {
    let body = {
      company: $("#iv-company").value.trim(),
      position: $("#iv-position").value.trim(),
      jobDescription: $("#iv-jd").value.trim(),
      messages: extraMessages || state.messages,
    };
    if (state.source === "pdf" && state.pdfText) {
      body.resumeText = state.pdfText;
    } else {
      body.resumeFileId = state.fileId;
    }
    return window.LLMSettings.inject(body);
  }

  // ---- 简历来源切换 & PDF 导入 ----
  function renderSrcUI() {
    const isPdf = state.source === "pdf";
    document.querySelectorAll(".iv-src-chip").forEach((c) => {
      c.classList.toggle("active", c.dataset.src === state.source);
    });
    $("#iv-file-label").classList.toggle("hidden", isPdf);
    $("#iv-pdf-zone").classList.toggle("hidden", !isPdf);
    const hasPdf = !!state.pdfText;
    $("#iv-pdf-card").classList.toggle("hidden", !hasPdf);
    const pick = $("#btn-pdf-pick");
    const label = hasPdf ? "重新选择 PDF" : "选择简历 PDF";
    let replaced = false;
    pick.childNodes.forEach((n) => {
      if (n.nodeType === 3 && n.textContent.trim()) { n.textContent = " " + label; replaced = true; }
    });
    if (!replaced) pick.appendChild(document.createTextNode(" " + label));
  }

  async function uploadPdf(file) {
    if (!file) return;
    cfgStatus("正在解析 PDF…", "busy");
    try {
      const fd = new FormData();
      fd.append("file", file);
      const c = window.LLMSettings.get();
      if (c.baseUrl) fd.append("baseUrl", c.baseUrl);
      if (c.apiKey) fd.append("apiKey", c.apiKey);
      if (c.model) fd.append("model", c.model);
      const r = await fetch(`${API}/interview/parse-pdf`, { method: "POST", body: fd });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || `解析失败（${r.status}）`);
      state.pdfText = data.text;
      state.pdfName = file.name;
      state.source = "pdf";
      renderSrcUI();
      $("#iv-pdf-name").textContent = file.name;
      $("#iv-pdf-badge").textContent =
        (data.method === "ocr" ? "AI OCR" : "文本抽取") + ` · ${data.pages} 页`;
      $("#iv-pdf-excerpt").textContent = data.text.slice(0, 120).replace(/\s+/g, " ") + "…";
      cfgStatus(`PDF 解析成功，可点击「开始面试」`, "ok");
    } catch (e) {
      cfgStatus("⚠️ " + e.message, "err");
    }
  }

  async function callInterview(messages) {
    const r = await fetch(`${API}/interview/ai-chat`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildBody(messages)),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || `请求失败（${r.status}）`);
    return data;
  }

  async function startInterview() {
    if (state.started || state.busy) return;
    if (!window.LLMSettings.hasConfig()) {
      cfgStatus("请先在「大模型设置」中配置 Base URL 与 API Key", "err");
      window.LLMSettings.open();
      return;
    }
    if (state.source === "pdf" && !state.pdfText) {
      cfgStatus("请先上传并解析一份简历 PDF", "err");
      return;
    }
    cfgStatus("");
    state.started = true;
    state.ended = false;
    state.messages = [];
    state.turns = 0;
    $("#chat-list").innerHTML = "";
    $("#btn-end").classList.remove("hidden");
    $("#btn-start").textContent = "面试进行中…";
    setBusy(true);
    updateTurn();
    addTyping();
    try {
      const data = await callInterview([]);
      removeTyping();
      const reply = data.reply || "我们开始吧。";
      state.messages.push({ role: "assistant", content: cleanReply(reply) });
      addMsg("assistant", reply);
      cfgStatus("面试已开始，请作答", "ok");
    } catch (e) {
      removeTyping();
      state.started = false;
      $("#btn-end").classList.add("hidden");
      $("#btn-start").innerHTML = "开始面试";
      cfgStatus(e.message, "err");
      addMsg("assistant", "⚠️ " + e.message);
    } finally {
      setBusy(false);
    }
  }

  async function sendAnswer() {
    if (!state.started || state.ended || state.busy) return;
    const input = $("#chat-input");
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    state.messages.push({ role: "user", content: text });
    addMsg("user", text);
    state.turns++;
    updateTurn();
    setBusy(true);
    addTyping();
    try {
      const data = await callInterview(state.messages);
      removeTyping();
      const reply = data.reply || "";
      state.messages.push({ role: "assistant", content: cleanReply(reply) });
      addMsg("assistant", reply);
    } catch (e) {
      removeTyping();
      addMsg("assistant", "⚠️ " + e.message);
    } finally {
      setBusy(false);
    }
  }

  async function endInterview() {
    if (!state.started || state.ended || state.busy) return;
    state.ended = true;
    const closing = "请结束这场面试，并对我的整体表现给出简要总结与改进建议。";
    state.messages.push({ role: "user", content: closing });
    addMsg("user", "（结束面试，请给出整体总结）");
    setBusy(true);
    addTyping();
    try {
      const data = await callInterview(state.messages);
      removeTyping();
      const reply = data.reply || "面试结束。";
      state.messages.push({ role: "assistant", content: cleanReply(reply) });
      addMsg("assistant", reply);
      cfgStatus("面试已结束", "ok");
    } catch (e) {
      removeTyping();
      addMsg("assistant", "⚠️ " + e.message);
    } finally {
      $("#btn-end").classList.add("hidden");
      $("#btn-start").textContent = "重新开始";
      $("#btn-start").disabled = false;
      state.started = false;
      setBusy(false);
      $("#btn-send").disabled = true;
      $("#chat-input").disabled = true;
    }
  }

  async function loadFiles() {
    try {
      const r = await fetch(`${API}/resume-files`);
      state.files = await r.json();
      const sel = $("#iv-file");
      sel.innerHTML = state.files.map((f) =>
        `<option value="${f.id}" ${f.isDefault ? "selected" : ""}>${esc(f.name)}${f.isDefault ? "（默认）" : ""}</option>`
      ).join("");
      const def = state.files.find((f) => f.isDefault) || state.files[0];
      state.fileId = def ? def.id : null;
      sel.value = state.fileId || "";
    } catch (e) { /* ignore */ }
  }

  function bind() {
    $("#btn-start").addEventListener("click", startInterview);
    $("#btn-send").addEventListener("click", sendAnswer);
    $("#btn-end").addEventListener("click", endInterview);
    $("#btn-settings").addEventListener("click", () => window.LLMSettings.open());
    $("#iv-file").addEventListener("change", (e) => { state.fileId = e.target.value; });
    // 简历来源切换
    document.querySelectorAll(".iv-src-chip").forEach((c) => {
      c.addEventListener("click", () => {
        if (state.started) return;
        state.source = c.dataset.src;
        renderSrcUI();
        cfgStatus("");
      });
    });
    // PDF 上传
    $("#btn-pdf-pick").addEventListener("click", () => $("#iv-pdf-input").click());
    $("#iv-pdf-input").addEventListener("change", (e) => {
      const f = e.target.files && e.target.files[0];
      if (f) uploadPdf(f);
      e.target.value = "";
    });
    $("#btn-pdf-del").addEventListener("click", () => {
      state.pdfText = "";
      state.pdfName = "";
      renderSrcUI();
      cfgStatus("已移除 PDF，请重新上传或改用简历档案");
    });
    $("#chat-input").addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); sendAnswer(); }
    });
  }

  async function init() {
    bind();
    renderSrcUI();
    await loadFiles();
    addMsg("assistant",
      "你好，我是 AI 面试官 🎙️\n\n配置好大模型后，填写目标公司与岗位，点击「开始面试」。" +
      "我会根据你的简历项目逐一提问，你作答后我会点评并继续追问。");
    if (!window.LLMSettings.hasConfig()) {
      cfgStatus("尚未配置大模型，点击右上角「大模型设置」", "err");
    }
  }
  document.addEventListener("DOMContentLoaded", init);
})();
