/* ============================================================
   主题引擎：HUD（深色战术青） ⇄ CREAM（奶白明亮） ⇄ COMIC（漫画书）
   - localStorage 持久化，全站同步
   - 内部键：hud / neon(CREAM) / comic(COMIC)
   用法：页面 head 引入本文件；任意元素 id="theme-toggle" 即为切换按钮，
        内含 [data-theme-label] 的节点会自动显示当前主题名。
   ============================================================ */
(function () {
  "use strict";
  var KEY = "resume-agent-theme";
  var ORDER = ["hud", "neon", "comic"];
  var LABELS = { hud: "HUD", neon: "CREAM", comic: "COMIC" };

  function get() {
    try {
      var t = localStorage.getItem(KEY);
      return ORDER.indexOf(t) >= 0 ? t : "hud";
    } catch (e) { return "hud"; }
  }
  function save(t) {
    try { localStorage.setItem(KEY, t); } catch (e) { /* ignore */ }
  }
  function apply(t) {
    document.documentElement.setAttribute("data-theme", t);
    var els = document.querySelectorAll("[data-theme-label]");
    els.forEach(function (el) { el.textContent = LABELS[t] || "HUD"; });
    // 供 CSS 通过 body 伪元素覆盖背景层
    document.querySelectorAll(".landing-body, .studio-body, .aic-body").forEach(function (b) {
      b.setAttribute("data-theme", t);
    });
  }
  function toggle() {
    var cur = get();
    var next = ORDER[(ORDER.indexOf(cur) + 1) % ORDER.length];
    save(next);
    apply(next);
  }

  // 切换按钮（事件委托，按钮可在任意位置）
  document.addEventListener("click", function (e) {
    var btn = e.target && e.target.closest ? e.target.closest("#theme-toggle") : null;
    if (btn) toggle();
  });

  apply(get());
  // head 中执行时 body 尚未解析，DOM 就绪后再应用一次（同步 body 上的 data-theme）
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { apply(get()); });
  }

  window.HudTheme = { get: get, set: function (t) { save(t); apply(t); }, toggle: toggle };
})();
