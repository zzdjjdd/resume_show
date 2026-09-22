/* ============================================================
 *  AI 智行助手 - 前端逻辑
 *  - Tab 切换
 *  - 设置：加载/保存/测试 LLM & 高德
 *  - 旅游：表单 → 后端 → Markdown 渲染、复制、下载
 *  - 聊天：流式输出 + ReAct 思考过程可折叠面板
 * ============================================================ */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const markedOpts = { breaks: true, gfm: true };

/* ------------- 通用：消息提示 ------------- */
function toast(msg, kind = "info") {
  const el = document.createElement("div");
  el.textContent = msg;
  el.style.cssText = `
    position: fixed; bottom: 30px; left: 50%; transform: translateX(-50%);
    padding: 12px 22px; border-radius: 999px; font-size: 13px;
    background: ${kind === "error" ? "#ef4444" : kind === "ok" ? "#10b981" : "#6366f1"};
    color: #fff; box-shadow: 0 10px 30px rgba(0,0,0,0.3); z-index: 999;
    opacity: 0; transition: opacity .25s ease;
  `;
  document.body.appendChild(el);
  requestAnimationFrame(() => (el.style.opacity = "1"));
  setTimeout(() => { el.style.opacity = "0"; setTimeout(() => el.remove(), 300); }, 2400);
}

/* ------------- Tab 切换 ------------- */
function bindTabs() {
  const tabs = $$(".nav-btn");
  const views = $$(".view");
  tabs.forEach(btn => {
    btn.addEventListener("click", () => {
      tabs.forEach(t => t.classList.toggle("active", t === btn));
      views.forEach(v => v.classList.toggle("active", v.id === `view-${btn.dataset.tab}`));
    });
  });
}

/* ============================================================
 *  设置
 * ============================================================ */
async function loadSettings() {
  try {
    const r = await fetch("/api/config");
    const cfg = await r.json();
    $("#llm-key").value = cfg.llm?.api_key || "";
    $("#llm-base").value = cfg.llm?.base_url || "";
    $("#llm-model").value = cfg.llm?.model || "";
    $("#amap-sse").value = cfg.amap?.sse_url || "";
    $("#amap-key").value = cfg.amap?.api_key || "";
    updateChatStatus(cfg);

    // MCP servers：默认两条占位
    const servers = cfg.mcp && Array.isArray(cfg.mcp.servers) && cfg.mcp.servers.length
      ? cfg.mcp.servers
      : [
          { name: "12306", url: "", enabled: false },
          { name: "hotel",  url: "", enabled: false },
        ];
    renderMcpList(servers);
  } catch (e) { /* 静默 */ }
}

function setTestResult(el, ok, msg) {
  el.textContent = msg || (ok ? "✓ 通过" : "✗ 失败");
  el.className = "test-result " + (ok ? "ok" : "err");
}

async function saveSection(section, payload) {
  const r = await fetch("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ section, payload }),
  });
  return r.json();
}

async function testConnection(path) {
  const r = await fetch(path, { method: "POST" });
  return r.json();
}

/* ---------------- MCP 服务器列表 ---------------- */

let mcpRowSeq = 0;

function renderMcpList(servers) {
  const box = $("#mcp-list");
  if (!box) return;
  box.innerHTML = "";
  (servers || []).forEach((s) => addMcpRow(s));
}

function addMcpRow(seed) {
  const box = $("#mcp-list");
  if (!box) return;
  const idx = ++mcpRowSeq;
  const row = document.createElement("div");
  row.className = "mcp-row";
  row.dataset.idx = String(idx);
  row.style.cssText = "display:grid; grid-template-columns: 140px 1fr 80px 80px 32px; gap:8px; align-items:center; margin-bottom: 8px;";
  row.innerHTML = `
    <input type="text" class="mcp-name field" placeholder="名称（英数）" value="${escapeAttr(seed?.name || "")}" />
    <input type="text" class="mcp-url field" placeholder="SSE 服务 URL，例如 https://.../sse" value="${escapeAttr(seed?.url || "")}" />
    <label class="toggle" title="启用">
      <input type="checkbox" class="mcp-enabled" ${seed?.enabled ? "checked" : ""} />
      <span class="toggle-track"><span class="toggle-dot"></span></span>
    </label>
    <button type="button" class="btn ghost small mcp-test">测试</button>
    <button type="button" class="btn ghost small mcp-del" title="删除">×</button>
  `;
  box.appendChild(row);
}

function escapeAttr(s) {
  return String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function collectMcpServers() {
  const rows = document.querySelectorAll("#mcp-list .mcp-row");
  const out = [];
  rows.forEach((row) => {
    out.push({
      name: row.querySelector(".mcp-name").value.trim(),
      url: row.querySelector(".mcp-url").value.trim(),
      enabled: row.querySelector(".mcp-enabled").checked,
    });
  });
  return out;
}

async function testMcpRow(row) {
  const name = row.querySelector(".mcp-name").value.trim();
  const url = row.querySelector(".mcp-url").value.trim();
  const btn = row.querySelector(".mcp-test");
  const resultEl = $("#test-mcp-result");

  btn.textContent = "…";
  btn.disabled = true;
  if (resultEl) {
    resultEl.textContent = `测试 ${name || "(未命名)"} 中…`;
    resultEl.className = "test-result";
  }

  try {
    const r = await fetch("/api/test/mcp", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, url }),
    });
    const out = await r.json();
    btn.textContent = out.ok ? "✓" : "✗";
    btn.title = out.message || "";
    btn.className = "btn ghost small mcp-test " + (out.ok ? "ok" : "err");
    // 把结果同步到主显示区（和 LLM/高德的"测试"按钮行为一致）
    if (resultEl) setTestResult(resultEl, out.ok, out.message);
  } catch (e) {
    btn.textContent = "✗";
    btn.title = "请求失败";
    btn.className = "btn ghost small mcp-test err";
    if (resultEl) setTestResult(resultEl, false, "请求失败：" + (e?.message || e));
  } finally {
    btn.disabled = false;
    // 5 秒后把按钮文字还原（结果保留在主显示区）
    setTimeout(() => {
      btn.textContent = "测试";
      btn.className = "btn ghost small mcp-test";
      btn.title = "";
    }, 5000);
  }
}

function bindMcpEvents() {
  const addBtn = $("#btn-add-mcp");
  if (addBtn) addBtn.addEventListener("click", () => addMcpRow({ name: "", url: "", enabled: false }));

  const saveBtn = $("#btn-save-mcp");
  if (saveBtn) saveBtn.addEventListener("click", async () => {
    const servers = collectMcpServers();
    const el = $("#test-mcp-result");
    el.textContent = "保存中…";
    el.className = "test-result";
    try {
      const out = await saveSection("mcp", { servers });
      if (out && out.ok) {
        toast("MCP 服务器配置已保存", "ok");
        setTestResult(el, true, `已保存 ${servers.length} 条服务器`);
      } else {
        setTestResult(el, false, "保存失败");
        toast("保存失败", "error");
      }
    } catch (e) {
      setTestResult(el, false, "请求失败");
    }
  });

  const box = $("#mcp-list");
  if (box) {
    box.addEventListener("click", (e) => {
      const row = e.target.closest(".mcp-row");
      if (!row) return;
      if (e.target.closest(".mcp-del")) {
        row.remove();
      } else if (e.target.closest(".mcp-test")) {
        testMcpRow(row);
      }
    });
  }
}

function bindSettings() {
  $("#btn-save-llm").addEventListener("click", async () => {
    const payload = {
      api_key: $("#llm-key").value.trim() || null,
      base_url: $("#llm-base").value.trim() || null,
      model: $("#llm-model").value.trim() || null,
    };
    const out = await saveSection("llm", payload);
    if (out.ok) {
      toast("LLM 配置已保存", "ok");
      updateChatStatus(out.config);
    } else toast("保存失败", "error");
  });

  $("#btn-test-llm").addEventListener("click", async () => {
    const el = $("#test-llm-result");
    el.textContent = "测试中…";
    el.className = "test-result";
    const out = await testConnection("/api/test/llm");
    setTestResult(el, out.ok, out.message);
    updateChatStatus();
  });

  $("#btn-save-amap").addEventListener("click", async () => {
    const payload = {
      sse_url: $("#amap-sse").value.trim() || null,
      api_key: $("#amap-key").value.trim() || null,
    };
    const out = await saveSection("amap", payload);
    if (out.ok) toast("高德配置已保存", "ok");
    else toast("保存失败", "error");
  });

  $("#btn-test-amap").addEventListener("click", async () => {
    const el = $("#test-amap-result");
    el.textContent = "测试中…";
    el.className = "test-result";
    const out = await testConnection("/api/test/amap");
    setTestResult(el, out.ok, out.message);
  });

  bindMcpEvents();
}

function updateChatStatus(cfg) {
  const status = $("#chat-status");
  if (!status) return;
  const llm = cfg && cfg.llm;
  const llmKey = (llm && llm.api_key) || $("#llm-key")?.value;
  const model = (llm && llm.model) || "MiniMax-M3";
  if (llmKey || (llm && llm.base_url)) {
    status.textContent = `模型：${model}`;
  } else {
    status.textContent = `模型：${model}（环境变量）`;
  }
}

/* ============================================================
 *  旅游模式（带 6 阶段进度条 + SSE 流式）
 * ============================================================ */
let currentMarkdown = "";

/* 固定的 6 个步骤（与后端 TRAVEL_STEPS 一一对应） */
const TRAVEL_STEPS = [
  { step: "prepare",   title: "准备参数", icon: "📋" },
  { step: "geocode",   title: "解析坐标", icon: "📍" },
  { step: "route",     title: "测算路线", icon: "🚗" },
  { step: "weather",   title: "查询天气", icon: "🌤️" },
  { step: "ai",        title: "AI 规划", icon: "🤖" },
  { step: "integrate", title: "整合结果", icon: "✨" },
];

/* 渲染进度面板（步骤条 + 当前活动文本流） */
function buildProgressPanel() {
  const wrap = document.createElement("div");
  wrap.className = "travel-progress";

  // 1) 步骤条
  const stepper = document.createElement("ol");
  stepper.className = "tp-stepper";
  TRAVEL_STEPS.forEach((s, idx) => {
    const li = document.createElement("li");
    li.className = "tp-step pending";
    li.dataset.step = s.step;
    li.innerHTML = `
      <div class="tp-dot"><span class="tp-icon">${s.icon}</span></div>
      <div class="tp-label">${s.title}</div>
    `;
    if (idx < TRAVEL_STEPS.length - 1) {
      const line = document.createElement("span");
      line.className = "tp-line";
      stepper.appendChild(li);
      stepper.appendChild(line);
    } else {
      stepper.appendChild(li);
    }
  });
  wrap.appendChild(stepper);

  // 2) 活动面板：当前阶段标题 + 实时文本流
  const activity = document.createElement("div");
  activity.className = "tp-activity";
  activity.innerHTML = `
    <div class="tp-act-head">
      <span class="tp-act-spinner"></span>
      <span class="tp-act-title">准备开始…</span>
    </div>
    <div class="tp-act-log"></div>
  `;
  wrap.appendChild(activity);

  const stepNodes = new Map();
  $$(".tp-step", stepper).forEach(li => stepNodes.set(li.dataset.step, li));
  const titleEl = activity.querySelector(".tp-act-title");
  const logEl = activity.querySelector(".tp-act-log");
  const headEl = activity.querySelector(".tp-act-head");

  function setStepState(stepName, state) {
    const li = stepNodes.get(stepName);
    if (!li) return;
    li.classList.remove("pending", "running", "done", "error");
    li.classList.add(state);
  }

  // AI 阶段专用：避免字符级流式输出把面板撑变形
  let aiThinkingActive = false;
  function showAiThinking() {
    if (aiThinkingActive) return;
    aiThinkingActive = true;
    const line = document.createElement("div");
    line.className = "tp-log-line tp-thinking";
    line.innerHTML =
      '<span class="tp-thinking-label">AI 正在生成行程</span>' +
      '<span class="tp-dots"><i></i><i></i><i></i></span>';
    logEl.appendChild(line);
  }
  function hideAiThinking() {
    aiThinkingActive = false;
    const t = logEl.querySelector(".tp-thinking");
    if (t) t.remove();
  }

  // 同时维护前后关系，让 line 跟随两侧状态变色
  function refreshLines() {
    const lines = $$(".tp-line", stepper);
    lines.forEach((line, idx) => {
      const before = TRAVEL_STEPS[idx];
      const beforeNode = stepNodes.get(before.step);
      line.classList.remove("active", "done");
      if (beforeNode.classList.contains("done") || beforeNode.classList.contains("error")) {
        line.classList.add("done");
      } else if (beforeNode.classList.contains("running")) {
        line.classList.add("active");
      }
    });
  }

  return {
    el: wrap,
    begin(stepName, meta) {
      setStepState(stepName, "running");
      titleEl.textContent = `${meta?.icon || ""}  ${meta?.title || stepName}…`;
      logEl.innerHTML = "";
      aiThinkingActive = false;
      // AI 阶段一开始就给一个稳定的"思考中"占位，避免空日志显得突兀
      if (stepName === "ai") showAiThinking();
      refreshLines();
    },
    delta(stepName, content) {
      if (!content) return;
      // AI 阶段：只显示思考动画，**不追加字符流**，避免日志行数膨胀拉伸面板
      if (stepName === "ai") return;
      const line = document.createElement("div");
      line.className = "tp-log-line";
      // 用 Markdown 渲染：支持 **加粗**、`code`、链接、行内换行等
      line.innerHTML = renderMarkdown(content);
      logEl.appendChild(line);
      logEl.scrollTop = logEl.scrollHeight;
    },
    end(stepName, summary, status) {
      setStepState(stepName, status === "error" ? "error" : "done");
      if (stepName === "ai") hideAiThinking();
      if (summary) {
        const line = document.createElement("div");
        line.className = "tp-log-line tp-log-summary";
        const prefix = status === "error" ? "✗ " : "✓ ";
        line.innerHTML = prefix + renderMarkdown(prefix + summary);
        logEl.appendChild(line);
      }
      refreshLines();
    },
    finalize(ok, message) {
      headEl.classList.add(ok ? "done" : "error");
      titleEl.textContent = ok ? "✅ 行程已生成" : "❌ 生成失败";
      if (!ok && message) {
        const line = document.createElement("div");
        line.className = "tp-log-line tp-log-error";
        line.textContent = message;
        logEl.appendChild(line);
      }
      const spinner = activity.querySelector(".tp-act-spinner");
      if (spinner) spinner.style.display = "none";
    },
  };
}

function bindTravel() {
  const form = $("#travel-form");
  const output = $("#md-output");
  const meta = $("#preview-meta");
  let busy = false;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (busy) return;
    const fd = new FormData(form);
    const prefs = $$('#pref-chips input:checked').map(i => i.value);
    const payload = {
      origin: fd.get("origin"),
      destination: fd.get("destination"),
      days: Number(fd.get("days") || 1),
      people: Number(fd.get("people") || 2),
      preferences: prefs,
      extra: fd.get("extra") || "",
      use_map: !!fd.get("use_map"),
    };

    busy = true;
    const panel = buildProgressPanel();
    output.innerHTML = "";
    output.appendChild(panel.el);
    meta.textContent = "生成中…";

    let accMarkdown = "";
    let enrichments = [];

    try {
      const r = await fetch("/api/travel/plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!r.ok || !r.body) {
        const txt = await r.text();
        panel.finalize(false, `请求失败：${txt}`);
        meta.textContent = "失败";
        busy = false;
        return;
      }

      const reader = r.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() || "";
        for (const ev of events) {
          const line = ev.split("\n").find(l => l.startsWith("data: "));
          if (!line) continue;
          const payloadStr = line.slice(6).trim();
          if (payloadStr === "[DONE]") continue;
          let data;
          try { data = JSON.parse(payloadStr); } catch { continue; }

          if (data.type === "step") {
            const meta2 = {
              title: data.title || (TRAVEL_STEPS.find(s => s.step === data.step) || {}).title,
              icon: data.icon || (TRAVEL_STEPS.find(s => s.step === data.step) || {}).icon,
            };
            if (data.phase === "begin") panel.begin(data.step, meta2);
            else if (data.phase === "delta") panel.delta(data.step, data.content || "");
            else if (data.phase === "end") panel.end(data.step, data.summary, data.status);
          } else if (data.type === "delta") {
            accMarkdown += data.content || "";
          } else if (data.type === "result") {
            if (data.ok) {
              accMarkdown = data.markdown || accMarkdown;
              enrichments = data.enrichments || [];
              currentMarkdown = accMarkdown;
              // 用最终 Markdown 替换整个进度面板
              output.innerHTML = marked.parse(accMarkdown, markedOpts);
              const enrich = enrichments.join(" · ");
              meta.textContent =
                (accMarkdown.length / 1024).toFixed(1) + " KB"
                + (enrich ? " · 已用高德数据" : "");
            } else {
              panel.finalize(false, data.message || "生成失败");
              meta.textContent = "失败";
            }
          } else if (data.type === "error") {
            panel.finalize(false, data.message || "未知错误");
            meta.textContent = "失败";
          } else if (data.type === "done") {
            // 终态由 result 事件驱动
          }
        }
      }
    } catch (err) {
      panel.finalize(false, "网络错误：" + err.message);
      meta.textContent = "网络错误";
    } finally {
      busy = false;
    }
  });

  $("#btn-copy").addEventListener("click", async () => {
    if (!currentMarkdown) return toast("暂无内容", "error");
    try {
      await navigator.clipboard.writeText(currentMarkdown);
      toast("已复制到剪贴板", "ok");
    } catch {
      toast("复制失败", "error");
    }
  });

  $("#btn-download").addEventListener("click", () => {
    if (!currentMarkdown) return toast("暂无内容", "error");
    const fd = new FormData($("#travel-form"));
    const dest = (fd.get("destination") || "trip").toString().trim();
    const blob = new Blob([currentMarkdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${dest}-${new Date().toISOString().slice(0, 10)}.md`;
    a.click();
    URL.revokeObjectURL(url);
  });

  // 展开 / 收起预览
  const toggleBtn = $("#btn-toggle-preview");
  const travelView = $("#view-travel");
  if (toggleBtn && travelView) {
    toggleBtn.addEventListener("click", () => {
      const expanded = travelView.classList.toggle("expanded");
      const icon = toggleBtn.querySelector(".pt-icon");
      const label = toggleBtn.querySelector(".pt-label");
      if (icon)   icon.textContent   = expanded ? "⤢" : "⛶";
      if (label)  label.textContent  = expanded ? "收起" : "展开";
      toggleBtn.title = expanded ? "收起预览" : "展开预览，给内容更多面积";
      toggleBtn.classList.toggle("expanded", expanded);
      // 让视口滚到顶部以便用户看到变化
      if (expanded) travelView.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }
}

/* ============================================================
 *  聊天模式（含 ReAct 思考过程面板）
 * ============================================================ */
const chatHistory = [];  // 仅历史消息文本，工具调用由后端处理
let busy = false;

/* ----- 简单 JSON 缩进展示 ----- */
function fmtJson(obj) {
  try {
    return JSON.stringify(obj, null, 2);
  } catch {
    return String(obj);
  }
}

/* ----- 把一行文本当作 Markdown 渲染（仅短行/段落，避免大块内容） ----- */
function renderMarkdown(content) {
  if (!content) return "";
  try {
    return marked.parse(String(content), { breaks: true, gfm: true });
  } catch {
    return escapeHtml(String(content));
  }
}

/* ----- 创建一条 assistant 消息（带可折叠 ReAct 面板） ----- */
function createAssistantMessage() {
  const win = $("#chat-window");
  const wrap = document.createElement("div");
  wrap.className = "msg from-assistant streaming";

  // 1) 主内容气泡
  const bubble = document.createElement("div");
  bubble.className = "msg-bubble msg-bubble-content";
  wrap.appendChild(bubble);

  // 2) ReAct 思考过程面板
  const traceWrap = document.createElement("div");
  traceWrap.className = "react-trace";
  traceWrap.innerHTML = `
    <details class="react-trace-details" open>
      <summary class="react-trace-summary">
        <span class="rt-icon">🪄</span>
        <span class="rt-title">思考过程</span>
        <span class="rt-count">0 步</span>
        <span class="rt-status running">运行中</span>
        <span class="rt-caret">▾</span>
      </summary>
      <ol class="react-trace-list"></ol>
    </details>
  `;
  wrap.appendChild(traceWrap);

  win.appendChild(wrap);
  win.scrollTop = win.scrollHeight;

  // 步骤状态机
  const steps = new Map();   // stepName -> { el, body, status, content, summary, data }
  let currentStepName = null;
  const list = traceWrap.querySelector(".react-trace-list");
  const countEl = traceWrap.querySelector(".rt-count");
  const statusEl = traceWrap.querySelector(".rt-status");

  function refreshCount() {
    countEl.textContent = `${list.children.length} 步`;
  }

  function ensureStep(stepName, meta) {
    if (steps.has(stepName)) return steps.get(stepName);
    const li = document.createElement("li");
    li.className = "react-step running";
    li.dataset.step = stepName;
    li.innerHTML = `
      <div class="react-step-head">
        <span class="rs-icon">${meta.icon || "•"}</span>
        <span class="rs-title">${meta.title || stepName}</span>
        <span class="rs-status">运行中</span>
      </div>
      <div class="react-step-body"></div>
    `;
    list.appendChild(li);
    const step = {
      el: li,
      body: li.querySelector(".react-step-body"),
      statusEl: li.querySelector(".rs-status"),
      iconEl: li.querySelector(".rs-icon"),
      titleEl: li.querySelector(".rs-title"),
      content: "",
      summary: "",
      data: null,
      status: "running",
    };
    steps.set(stepName, step);
    refreshCount();
    return step;
  }

  function setStepStatus(stepName, status) {
    const s = steps.get(stepName);
    if (!s) return;
    s.status = status;
    s.el.classList.remove("running", "done", "error");
    s.el.classList.add(status);
    s.statusEl.textContent = status === "error" ? "失败" : status === "done" ? "完成" : "运行中";
  }

  return {
    wrap, bubble, traceWrap,
    beginStep(stepName, meta) {
      currentStepName = stepName;
      const s = ensureStep(stepName, meta || {});
      setStepStatus(stepName, "running");
      // 滚动到最新
      win.scrollTop = win.scrollHeight;
      return s;
    },
    appendStepDelta(stepName, content) {
      const s = ensureStep(stepName, STEP_META[stepName] || {});
      s.content += content;
      s.body.textContent = s.content;
      win.scrollTop = win.scrollHeight;
    },
    endStep(stepName, summary, data, status = "done") {
      const s = ensureStep(stepName, STEP_META[stepName] || {});
      s.summary = summary || "";
      s.data = data || null;
      // 结构化数据（args/result）单独渲染
      const dataHtml = (data && (data.args || data.result))
        ? `<div class="react-step-data">${escapeHtml(fmtJson(data))}</div>`
        : "";
      const summaryHtml = s.summary
        ? `<div class="react-step-summary">${escapeHtml(s.summary)}</div>`
        : "";
      s.body.innerHTML = (s.content ? `<div class="react-step-content">${escapeHtml(s.content)}</div>` : "")
        + summaryHtml + dataHtml;
      setStepStatus(stepName, status);
      win.scrollTop = win.scrollHeight;
    },
    finish(statusText) {
      statusEl.textContent = statusText || "已完成";
      statusEl.className = "rt-status done";
      // 收尾时把内容也滚到位
      win.scrollTop = win.scrollHeight;
    },
  };
}

/* 后端返回 step 名 -> 前端元数据（兜底，后端也会带 title/icon） */
const STEP_META = {
  thought:     { title: "思考",     icon: "🧠" },
  intent:      { title: "意图识别", icon: "🎯" },
  tool_select: { title: "选择工具", icon: "🔧" },
  args:        { title: "构造参数", icon: "📦" },
  action:      { title: "执行调用", icon: "⚡" },
  observation: { title: "观察结果", icon: "👁️" },
  iterate:     { title: "迭代判断", icon: "🔄" },
};

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

function appendMessage(role, content, opts = {}) {
  const win = $("#chat-window");
  const wrap = document.createElement("div");
  wrap.className = `msg from-${role}` + (opts.streaming ? " streaming" : "");
  const bubble = document.createElement("div");
  bubble.className = "msg-bubble";

  if (role === "tool") {
    const safeName = escapeHtml(opts.name || "");
    let pretty = "";
    try { pretty = JSON.stringify(opts.result ?? {}, null, 2); }
    catch { pretty = String(opts.result ?? ""); }
    bubble.innerHTML = `
      <details class="tool-result">
        <summary class="tool-result-head">
          <span class="tr-icon">📍</span>
          <span class="tr-name">工具结果 · ${safeName}</span>
          <span class="tool-toggle-hint">▸</span>
        </summary>
        <pre class="tool-result-body">${escapeHtml(pretty)}</pre>
      </details>
    `;
  } else if (role === "think") {
    bubble.textContent = `💭 思考中…\n${content || ""}`;
  } else if (role === "assistant" && content) {
    bubble.innerHTML = marked.parse(content, markedOpts);
  } else {
    bubble.textContent = content || "";
  }

  wrap.appendChild(bubble);
  win.appendChild(wrap);
  win.scrollTop = win.scrollHeight;
  return { wrap, bubble };
}

function bindChat() {
  const form = $("#chat-form");
  const input = $("#chat-text");

  $("#btn-clear-chat").addEventListener("click", () => {
    chatHistory.length = 0;
    const win = $("#chat-window");
    win.innerHTML = "";
    appendMessage("system", "👋 新的对话已就绪，请问你想了解什么？");
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (busy) return;
    const text = input.value.trim();
    if (!text) return;

    input.value = "";
    busy = true;

    appendMessage("user", text);
    chatHistory.push({ role: "user", content: text });

    const aMsg = createAssistantMessage();
    let acc = "";
    let gotError = false;

    try {
      const r = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: chatHistory }),
      });
      if (!r.ok || !r.body) {
        const txt = await r.text();
        aMsg.bubble.innerHTML = `<span style="color:#e11d48">⚠️ 请求失败：${escapeHtml(txt)}</span>`;
        aMsg.wrap.classList.remove("streaming");
        aMsg.finish("失败");
        busy = false;
        return;
      }
      const reader = r.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() || "";
        for (const ev of events) {
          const line = ev.split("\n").find(l => l.startsWith("data: "));
          if (!line) continue;
          const payload = line.slice(6).trim();
          if (payload === "[DONE]") continue;
          let data;
          try { data = JSON.parse(payload); } catch { continue; }

          if (data.type === "delta") {
            acc += data.content;
            aMsg.bubble.innerHTML = marked.parse(acc, markedOpts);
            $("#chat-window").scrollTop = $("#chat-window").scrollHeight;
          } else if (data.type === "thinking") {
            // 兼容旧字段，转写到 thought 步骤
            aMsg.appendStepDelta("thought", data.content);
          } else if (data.type === "step") {
            const meta = {
              title: data.title || (STEP_META[data.step] || {}).title,
              icon: data.icon || (STEP_META[data.step] || {}).icon,
            };
            if (data.phase === "begin") {
              aMsg.beginStep(data.step, meta);
            } else if (data.phase === "delta") {
              aMsg.appendStepDelta(data.step, data.content || "");
            } else if (data.phase === "end") {
              aMsg.endStep(data.step, data.summary, data.data, data.status || "done");
            }
          } else if (data.type === "tool") {
            // 外部 MCP 工具标注「🔌 来自 xxx MCP」
            const label = data.server ? `🔌 来自 ${data.server} MCP` : "";
            appendMessage("tool", label, { name: data.name, result: data.result });
            $("#chat-window").scrollTop = $("#chat-window").scrollHeight;
          } else if (data.type === "error") {
            aMsg.bubble.innerHTML = `<span style="color:#e11d48">⚠️ ${escapeHtml(data.message)}</span>`;
            gotError = true;
          } else if (data.type === "done") {
            // 终态：done 由后端 iterate 步骤的 end 事件传递
          } else if (data.type === "tools") {
            // 工具汇总已在前端逐步展示，可忽略
          }
        }
      }

      aMsg.wrap.classList.remove("streaming");
      chatHistory.push({ role: "assistant", content: acc });
      aMsg.finish(gotError ? "失败" : "已完成");
    } catch (err) {
      aMsg.bubble.innerHTML = `<span style="color:#e11d48">⚠️ 网络异常：${escapeHtml(err.message)}</span>`;
      aMsg.wrap.classList.remove("streaming");
      aMsg.finish("失败");
    } finally {
      busy = false;
    }
  });
}

/* ============================================================
 *  启动
 * ============================================================ */
window.addEventListener("DOMContentLoaded", () => {
  bindTabs();
  bindSettings();
  bindTravel();
  bindChat();
  loadSettings();
});