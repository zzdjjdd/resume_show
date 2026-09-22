/* ============================================================
   LLM 设置模块（共享）
   - 在 localStorage 持久化 baseurl / apikey / model（OpenAI 协议）
   - 提供设置弹窗、配置读取、注入到 AI 请求体
   用法：页面引入本文件后，调用 window.LLMSettings.open() 打开设置；
        发起 AI 请求前用 window.LLMSettings.inject(body) 注入配置。
   ============================================================ */
(function () {
  "use strict";
  var KEY = "resume-agent-llm-config";

  function get() {
    try { return JSON.parse(localStorage.getItem(KEY)) || {}; }
    catch (e) { return {}; }
  }
  function save(cfg) {
    localStorage.setItem(KEY, JSON.stringify(cfg || {}));
  }
  function hasConfig() {
    var c = get();
    return !!(c.baseUrl && c.apiKey);
  }
  function inject(body) {
    var c = get();
    if (c.baseUrl) body.baseUrl = c.baseUrl;
    if (c.apiKey) body.apiKey = c.apiKey;
    if (c.model) body.model = c.model;
    return body;
  }

  // ---- 弹窗 DOM（懒构建一次）----
  var backdrop = null;
  function build() {
    if (backdrop) return;
    backdrop = document.createElement("div");
    backdrop.className = "llm-modal-backdrop hidden";
    backdrop.innerHTML =
      '<div class="llm-modal">' +
        '<div class="llm-modal-head">' +
          '<span class="llm-modal-title">⚙️ 大模型设置</span>' +
          '<button type="button" class="llm-x" data-act="close">✕</button>' +
        '</div>' +
        '<p class="llm-tip">使用 OpenAI 兼容协议连接，只需填写 Base URL 与 API Key。</p>' +
        '<label class="llm-label">Base URL' +
          '<input id="llm-baseurl" class="llm-input" placeholder="https://api.openai.com/v1" />' +
        '</label>' +
        '<label class="llm-label">API Key' +
          '<input id="llm-apikey" class="llm-input" type="password" placeholder="sk-..." autocomplete="off" />' +
        '</label>' +
        '<label class="llm-label">模型（可选）' +
          '<input id="llm-model" class="llm-input" placeholder="gpt-4o-mini / qwen-plus …" />' +
        '</label>' +
        '<div class="llm-status" id="llm-status"></div>' +
        '<div class="llm-modal-foot">' +
          '<button type="button" class="llm-btn ghost" data-act="test">测试连接</button>' +
          '<span style="flex:1"></span>' +
          '<button type="button" class="llm-btn" data-act="cancel">取消</button>' +
          '<button type="button" class="llm-btn primary" data-act="save">保存</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(backdrop);
    backdrop.addEventListener("click", function (e) {
      if (e.target === backdrop) close();
      var act = e.target.closest ? e.target.closest("[data-act]") : null;
      if (!act) return;
      var a = act.getAttribute("data-act");
      if (a === "close" || a === "cancel") close();
      if (a === "save") doSave();
      if (a === "test") doTest();
    });
  }

  function fill() {
    var c = get();
    document.getElementById("llm-baseurl").value = c.baseUrl || "";
    document.getElementById("llm-apikey").value = c.apiKey || "";
    document.getElementById("llm-model").value = c.model || "";
    setStatus("", "");
  }
  function setStatus(text, cls) {
    var el = document.getElementById("llm-status");
    el.textContent = text || "";
    el.className = "llm-status" + (cls ? " " + cls : "");
  }
  function collect() {
    return {
      baseUrl: document.getElementById("llm-baseurl").value.trim(),
      apiKey: document.getElementById("llm-apikey").value.trim(),
      model: document.getElementById("llm-model").value.trim(),
    };
  }
  function doSave() {
    save(collect());
    setStatus("已保存 ✓", "ok");
    setTimeout(close, 500);
  }
  function doTest() {
    var c = collect();
    if (!c.baseUrl || !c.apiKey) { setStatus("请先填写 Base URL 与 API Key", "err"); return; }
    setStatus("测试中…", "busy");
    var url = c.baseUrl.replace(/\/+$/, "") + "/chat/completions";
    fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Authorization": "Bearer " + c.apiKey },
      body: JSON.stringify({
        model: c.model || "gpt-4o-mini",
        messages: [{ role: "user", content: "hi" }],
        max_tokens: 5,
      }),
    }).then(function (r) {
      if (r.ok) setStatus("连接成功 ✓", "ok");
      else return r.text().then(function (t) { setStatus("连接失败（" + r.status + "）：" + t.slice(0, 120), "err"); });
    }).catch(function (e) {
      setStatus("连接失败：" + e.message, "err");
    });
  }

  function open() {
    build();
    fill();
    backdrop.classList.remove("hidden");
  }
  function close() {
    if (backdrop) backdrop.classList.add("hidden");
  }

  // 暴露到全局
  window.LLMSettings = { get: get, save: save, hasConfig: hasConfig, inject: inject, open: open, close: close };

  // 注入弹窗样式一次
  if (!document.getElementById("llm-settings-css")) {
    var st = document.createElement("style");
    st.id = "llm-settings-css";
    st.textContent =
      ".llm-modal-backdrop{position:fixed;inset:0;background:rgba(2,6,23,.66);backdrop-filter:blur(6px);display:grid;place-items:center;z-index:80;padding:20px}" +
      ".llm-modal-backdrop.hidden{display:none}" +
      ".llm-modal{width:min(460px,100%);background:rgba(10,15,32,.96);border:1px solid rgba(34,211,238,.28);border-radius:12px;box-shadow:0 30px 80px -20px rgba(0,0,0,.8),0 0 40px rgba(34,211,238,.1);padding:22px;animation:llmIn .22s ease;position:relative;color:#e5f2ff}" +
      ".llm-modal::before{content:'';position:absolute;top:-1px;left:-1px;width:13px;height:13px;border-top:1.5px solid #22d3ee;border-left:1.5px solid #22d3ee;opacity:.75;pointer-events:none}" +
      ".llm-modal::after{content:'';position:absolute;bottom:-1px;right:-1px;width:13px;height:13px;border-bottom:1.5px solid #22d3ee;border-right:1.5px solid #22d3ee;opacity:.75;pointer-events:none}" +
      "@keyframes llmIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}" +
      ".llm-modal-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:6px}" +
      ".llm-modal-title{font-size:16px;font-weight:800;color:#22d3ee;letter-spacing:.04em}" +
      ".llm-x{border:none;background:transparent;font-size:15px;color:#64748b;cursor:pointer;padding:4px 8px;border-radius:6px}" +
      ".llm-x:hover{background:rgba(34,211,238,.1);color:#22d3ee}" +
      ".llm-tip{font-size:12.5px;color:#94a3b8;margin:0 0 14px;line-height:1.6}" +
      ".llm-label{display:block;font-size:12.5px;font-weight:700;color:#94a3b8;margin-bottom:12px;font-family:Consolas,monospace;letter-spacing:.06em}" +
      ".llm-input{width:100%;margin-top:5px;padding:10px 12px;border:1.5px solid rgba(34,211,238,.16);border-radius:8px;font-size:13.5px;outline:none;transition:border-color .15s,box-shadow .15s;background:rgba(2,6,23,.6);color:#e5f2ff}" +
      ".llm-input::placeholder{color:#475569}" +
      ".llm-input:focus{border-color:rgba(34,211,238,.55);box-shadow:0 0 0 3px rgba(34,211,238,.1),0 0 14px rgba(34,211,238,.12)}" +
      ".llm-status{font-size:12.5px;margin:2px 0 10px;min-height:18px;font-family:Consolas,monospace}" +
      ".llm-status.ok{color:#4ade80}.llm-status.err{color:#f87171}.llm-status.busy{color:#22d3ee}" +
      ".llm-modal-foot{display:flex;align-items:center;gap:9px}" +
      ".llm-btn{font-size:13px;font-weight:700;padding:9px 18px;border-radius:8px;border:none;cursor:pointer;transition:all .18s}" +
      ".llm-btn.primary{background:linear-gradient(135deg,#06b6d4,#0ea5e9,#22d3ee);color:#03202b;box-shadow:0 0 18px rgba(34,211,238,.3);border:1px solid rgba(165,243,252,.4)}" +
      ".llm-btn.primary:hover{transform:translateY(-1px);box-shadow:0 0 26px rgba(34,211,238,.5)}" +
      ".llm-btn.ghost{background:rgba(34,211,238,.06);color:#94a3b8;border:1px solid rgba(34,211,238,.16)}.llm-btn.ghost:hover{background:rgba(34,211,238,.12);color:#22d3ee}" +
      ".llm-btn:not(.primary):not(.ghost){background:rgba(2,6,23,.5);color:#94a3b8;border:1px solid rgba(34,211,238,.16)}.llm-btn:not(.primary):not(.ghost):hover{color:#22d3ee;border-color:rgba(34,211,238,.4)}";
    document.head.appendChild(st);
  }
})();
