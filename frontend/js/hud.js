/* ============================================================
   HUD 辅助脚本：舰桥时间同步（更新所有 [data-hud-clock] 元素）
   并提供 HudRender.message：把 AI 回复中的 <think>…</think> 块
   渲染为可点击展开/收起的「思考过程」折叠块
   ============================================================ */
(function () {
  "use strict";
  function pad(n) { return String(n).padStart(2, "0"); }
  function tick() {
    var els = document.querySelectorAll("[data-hud-clock]");
    if (!els.length) return;
    var d = new Date();
    var s = pad(d.getHours()) + ":" + pad(d.getMinutes()) + ":" + pad(d.getSeconds());
    els.forEach(function (el) { el.textContent = s; });
  }
  tick();
  setInterval(tick, 1000);

  /* —— 消息富渲染：抽出 <think> 块为可折叠组件 + 轻量 Markdown —— */
  var THINK_RE = /<think>([\s\S]*?)<\/think>/gi;

  function escHtml(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  /* 行内：**加粗** / *斜体* / `代码` / [链接](url) */
  function inline(text) {
    var codes = [];
    var s = escHtml(text).replace(/`([^`]+)`/g, function (_, c) {
      codes.push(c);
      return "\u0001" + (codes.length - 1) + "\u0001";
    });
    s = s
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>")
      .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g,
        '<a href="$2" target="_blank" rel="noopener">$1</a>');
    s = s.replace(/\u0001(\d+)\u0001/g, function (_, i) {
      return "<code>" + codes[+i] + "</code>";
    });
    return s;
  }

  /* 块级：标题 / 列表 / 引用 / 分割线 / 段落（换行转 <br>） */
  function blocks(text) {
    var lines = String(text).split("\n");
    var html = "", list = null, quote = [];
    function closeList() { if (list) { html += "</ul>"; list = null; } }
    function closeQuote() {
      if (quote.length) { html += "<blockquote>" + quote.map(inline).join("<br>") + "</blockquote>"; quote = []; }
    }
    for (var i = 0; i < lines.length; i++) {
      var t = lines[i].trim();
      var m;
      if (!t) { closeList(); closeQuote(); continue; }
      if ((m = t.match(/^(#{1,4})\s+(.+)$/))) {
        closeList(); closeQuote();
        html += '<div class="md-h md-h' + m[1].length + '">' + inline(m[2]) + "</div>";
      } else if (/^(-{3,}|\*{3,}|_{3,})$/.test(t)) {
        closeList(); closeQuote();
        html += "<hr>";
      } else if ((m = t.match(/^>\s?(.*)$/))) {
        closeList(); quote.push(m[1]);
      } else if ((m = t.match(/^[-*•]\s+(.+)$/)) || (m = t.match(/^\d+[.、)]\s+(.+)$/))) {
        closeQuote();
        if (!list) { html += '<ul class="md-list">'; list = true; }
        html += "<li>" + inline(m[1]) + "</li>";
      } else {
        closeList(); closeQuote();
        html += "<p>" + inline(t) + "</p>";
      }
    }
    closeList(); closeQuote();
    return html;
  }

  function buildThink(details, thinkText) {
    var sum = document.createElement("summary");
    sum.className = "think-sum";
    sum.innerHTML = '<span class="think-ico">💭</span>思考过程<span class="think-hint">点击展开 / 收起</span>';
    var body = document.createElement("div");
    body.className = "think-body";
    body.textContent = thinkText.trim();
    details.appendChild(sum);
    details.appendChild(body);
  }

  window.HudRender = {
    /* 完整消息渲染：think 折叠块 + Markdown（文本均经过转义，安全） */
    message: function (bubble, content) {
      bubble.textContent = "";
      bubble.classList.add("md-content");
      var src = String(content == null ? "" : content);
      var last = 0;
      var m;
      THINK_RE.lastIndex = 0;
      while ((m = THINK_RE.exec(src)) !== null) {
        if (m.index > last) {
          var seg = src.slice(last, m.index);
          if (seg.trim()) bubble.insertAdjacentHTML("beforeend", blocks(seg));
        }
        var details = document.createElement("details");
        details.className = "think-block";
        buildThink(details, m[1]);
        bubble.appendChild(details);
        last = m.index + m[0].length;
      }
      if (last < src.length) {
        var rest = src.slice(last);
        if (rest.trim()) bubble.insertAdjacentHTML("beforeend", blocks(rest));
      }
    },
    /* 纯 Markdown（无 think 处理） */
    markdown: function (bubble, content) {
      bubble.textContent = "";
      bubble.classList.add("md-content");
      bubble.insertAdjacentHTML("beforeend", blocks(String(content == null ? "" : content)));
    },
  };

  /* —— Landing 滚动显现：进入视口时逐张浮现卡片 —— */
  (function initScrollReveal() {
    if (!document.body.classList.contains("landing-body")) return;
    if (!("IntersectionObserver" in window)) return;
    var targets = document.querySelectorAll(
      ".landing-body .feature-card, .landing-body .step-card, .landing-body .final-cta"
    );
    if (!targets.length) return;
    /* 同组内按序错峰延迟 */
    var groupIdx = {};
    targets.forEach(function (t) {
      var g = t.parentElement || document.body;
      groupIdx[g.className] = (groupIdx[g.className] || 0);
      t.style.transitionDelay = (groupIdx[g.className] * 0.09) + "s";
      groupIdx[g.className] += 1;
      t.classList.add("sr");
    });
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) {
          en.target.classList.add("sr-in");
          io.unobserve(en.target);
        }
      });
    }, { threshold: 0.15, rootMargin: "0px 0px -30px 0px" });
    targets.forEach(function (t) { io.observe(t); });
  })();
})();
