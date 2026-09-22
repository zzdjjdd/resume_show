/* ==========================================================================
   index.html 专用 — Scrollytelling 动画 & 微交互
   --------------------------------------------------------------------------
   依赖：common.js（暴露 App.bindReveal / App.bindTopnav / App.bindScrollProgress）
   设计原则：
     1. IntersectionObserver 触发 reveal（继承 common.bindReveal）
     2. sticky 章节的进度感知：用 IntersectionObserver 算 "in-view 比例"，
        写入 data-progress,再用 CSS 变量驱动子元素动画
     3. 键盘导航：↑/↓/PageUp/PageDown/Home/End 跳分镜
     4. prefers-reduced-motion：直接 disable 全部滚动驱动动画
   ========================================================================== */
(function () {
  'use strict';

  const App = window.App;
  if (!App) return;

  // ------------------------------------------------------------------
  // 0. 减少动效偏好 — 一票否决
  // ------------------------------------------------------------------
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  document.addEventListener('DOMContentLoaded', () => {
    // 0.1 基础：让 .reveal 元素在进入视口时加 .is-visible
    //       common.js 已有 bindReveal()，但它在 boot() 里就跑了，所以这里
    //       不需要重复调用；但页面脚本启动时机可能晚于 boot，所以保险起见
    //       直接观察一次未激活的 .reveal
    bindRevealManual();

    if (reducedMotion) {
      // 全部 reveal 立即可见，跳过其余动画
      document.querySelectorAll('.reveal').forEach((el) => el.classList.add('is-visible'));
      return;
    }

    // 0.2 sticky 章节的进度感知（只对 .scene-route / .scene-chat 启用，
    //     因为它们用 sticky 主画面 + 副文案的 "stagger" 效果收益最大）
    bindStickyProgress('.scene-route', onRouteProgress);
    bindStickyProgress('.scene-chat', onChatProgress);

    // 0.3 路径绘制（Scene 2 地图 SVG）
    bindRouteDraw();

    // 0.4 数字递增（Hero meta）
    bindNumberTween();

    // 0.5 章节序号滚动（可选：让 .kicker 的"#"数字跟进度联动）
    bindSceneProgress('.scene', (scene, p) => {
      const idx = sceneIndex(scene);
      if (idx >= 0) {
        scene.style.setProperty('--scene-progress', p.toFixed(3));
      }
    });

    // 0.6 键盘导航
    bindKeyboardNav();
  });

  // ------------------------------------------------------------------
  // 1. 兜底 reveal（如果 common.boot() 比本脚本早完成，重复触发无害）
  // ------------------------------------------------------------------
  function bindRevealManual() {
    const els = document.querySelectorAll('.reveal:not(.is-visible)');
    if (!('IntersectionObserver' in window)) {
      els.forEach((el) => el.classList.add('is-visible'));
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            e.target.classList.add('is-visible');
            io.unobserve(e.target);
          }
        }
      },
      { threshold: 0.12, rootMargin: '0px 0px -8% 0px' }
    );
    els.forEach((el) => io.observe(el));
  }

  // ------------------------------------------------------------------
  // 2. sticky 进度：让 sticky 元素在视口内的"进入比例"可被 CSS / JS 感知
  //
  // 用法：bindStickyProgress('.scene-route', (p, scene) => { ... })
  //   p ∈ [0, 1]：0 = sticky 元素刚顶到 nav 下方；1 = sticky 元素即将被推走
  // ------------------------------------------------------------------
  function bindStickyProgress(selector, handler) {
    const scenes = document.querySelectorAll(selector);
    if (!scenes.length) return;

    const navH = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--nav-h')) || 64;

    scenes.forEach((scene) => {
      const update = () => {
        const r = scene.getBoundingClientRect();
        const top = r.top;
        const h = r.height;
        // sticky 容器在 viewport 中的可视范围
        const viewport = window.innerHeight;
        // sticky "贴住"窗口可视起点：top = navH；离开：top = navH - (h - viewport)
        const start = navH;
        const end = navH - (h - viewport);
        let p = 0;
        if (h <= viewport) {
          // scene 太短,直接给 1
          p = 1;
        } else if (top <= start && top >= end) {
          p = (start - top) / (start - end);
        } else if (top < end) {
          p = 1;
        } else {
          p = 0;
        }
        p = Math.max(0, Math.min(1, p));
        scene.style.setProperty('--scene-p', p.toFixed(3));
        handler(p, scene);
      };
      update();
      window.addEventListener('scroll', update, { passive: true });
      window.addEventListener('resize', update);
    });
  }

  // ------------------------------------------------------------------
  // 2.1 Scene 2 进度 → 工具 tag 依次出现 + 路径透明度增强
  // ------------------------------------------------------------------
  function onRouteProgress(p, scene) {
    // 让 6 个 tag 按 p ∈ [0,1] 依次出现
    const tags = scene.querySelectorAll('.scene-route__tools .tag');
    tags.forEach((tag, i) => {
      const threshold = (i + 1) / (tags.length + 1); // 0.14, 0.28, 0.42, 0.57, 0.71, 0.85
      tag.classList.toggle('is-on', p >= threshold);
    });
  }

  // ------------------------------------------------------------------
  // 2.2 Scene 3 进度 → 输入框 caret 闪烁加速 / 消息卡片错位浮起
  // ------------------------------------------------------------------
  function onChatProgress(p, scene) {
    // 聊天卡片从 p=0 到 p=0.5 之间依次浮入
    const msgs = scene.querySelectorAll('.scene-chat__msg, .scene-chat__tool');
    msgs.forEach((m, i) => {
      const t = i / Math.max(1, msgs.length);
      const threshold = t * 0.5;
      m.classList.toggle('is-on', p >= threshold);
    });
  }

  // ------------------------------------------------------------------
  // 3. 路径绘制：Scene 2 的 SVG 路径在进入视口时画出来
  // ------------------------------------------------------------------
  function bindRouteDraw() {
    const path = document.querySelector('.scene-route__map-route svg path');
    if (!path) return;

    const length = path.getTotalLength();
    path.style.strokeDasharray = length;
    path.style.strokeDashoffset = length;
    path.style.transition = 'stroke-dashoffset 1400ms cubic-bezier(0.22, 1, 0.36, 1)';

    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            path.style.strokeDashoffset = '0';
            io.disconnect();
          }
        }
      },
      { threshold: 0.3 }
    );
    io.observe(path);
  }

  // ------------------------------------------------------------------
  // 4. Hero meta 数字递增（只跑一次，进入视口后）
  // ------------------------------------------------------------------
  function bindNumberTween() {
    const nums = document.querySelectorAll('.scene-hero__meta-item .num');
    if (!nums.length) return;

    const targets = Array.from(nums).map((el) => {
      const raw = el.textContent.trim();
      // 保留 "∞" 之类不可数值化的原样
      if (raw === '∞' || isNaN(parseFloat(raw))) return { el, target: raw, raw };
      const n = parseFloat(raw);
      return { el, target: n, raw };
    });

    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (!e.isIntersecting) continue;
          io.disconnect();
          targets.forEach((t) => {
            if (typeof t.target !== 'number') return;
            const dur = 1100;
            const start = performance.now();
            const tick = (now) => {
              const t01 = Math.min(1, (now - start) / dur);
              // ease-out
              const eased = 1 - Math.pow(1 - t01, 3);
              const v = Math.round(t.target * eased * 10) / 10;
              // 整数显示
              t.el.textContent = Number.isInteger(t.target) ? Math.round(v) : v;
              if (t01 < 1) requestAnimationFrame(tick);
            };
            requestAnimationFrame(tick);
          });
        }
      },
      { threshold: 0.4 }
    );
    io.observe(nums[0]);
  }

  // ------------------------------------------------------------------
  // 5. 通用 scene 进度回调（这里只写一个 no-op 风格，可被扩展）
  // ------------------------------------------------------------------
  function bindSceneProgress(selector, handler) {
    const scenes = Array.from(document.querySelectorAll(selector));
    if (!scenes.length) return;
    const navH = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--nav-h')) || 64;

    const onScroll = () => {
      scenes.forEach((s) => {
        const r = s.getBoundingClientRect();
        const viewport = window.innerHeight;
        const start = navH;
        const end = navH - (r.height - viewport);
        let p = 0;
        if (r.top <= start && r.top >= end) {
          p = (start - r.top) / (start - end);
        } else if (r.top < end) {
          p = 1;
        }
        p = Math.max(0, Math.min(1, p));
        handler(s, p);
      });
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
  }

  function sceneIndex(scene) {
    const all = Array.from(document.querySelectorAll('.scene'));
    return all.indexOf(scene);
  }

  // ------------------------------------------------------------------
  // 6. 键盘导航
  //    ↑/PageUp:  上一分镜（顶部时往上滚回顶）
  //    ↓/PageDown: 下一分镜
  //    Home: 顶部；End: 底部
  //    在输入框聚焦时禁用（虽然首页没输入框，但防一手）
  // ------------------------------------------------------------------
  function bindKeyboardNav() {
    const scenes = Array.from(document.querySelectorAll('.scene'));
    if (!scenes.length) return;

    let lastKey = 0;
    const debounce = 380; // ms

    const isTextField = (el) => {
      if (!el) return false;
      const tag = el.tagName;
      return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable;
    };

    document.addEventListener('keydown', (e) => {
      if (isTextField(e.target)) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      const now = Date.now();
      if (now - lastKey < debounce) return;

      const scrollY = window.scrollY;
      const navH = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--nav-h')) || 64;
      const docH = document.documentElement.scrollHeight;
      const winH = window.innerHeight;

      // 找当前所在的 scene（中心点）
      const center = scrollY + winH / 2;
      let currentIdx = 0;
      scenes.forEach((s, i) => {
        const top = s.offsetTop;
        const bottom = top + s.offsetHeight;
        if (center >= top && center < bottom) currentIdx = i;
      });

      let targetY = null;
      switch (e.key) {
        case 'ArrowDown':
        case 'PageDown':
        case ' ': // 空格：下一屏
          e.preventDefault();
          targetY = scenes[currentIdx + 1]
            ? scenes[currentIdx + 1].offsetTop
            : docH - winH;
          break;
        case 'ArrowUp':
        case 'PageUp':
          e.preventDefault();
          targetY = currentIdx > 0
            ? scenes[currentIdx - 1].offsetTop
            : 0;
          break;
        case 'Home':
          e.preventDefault();
          targetY = 0;
          break;
        case 'End':
          e.preventDefault();
          targetY = docH - winH;
          break;
        default:
          return;
      }

      if (targetY !== null) {
        window.scrollTo({ top: targetY, behavior: reducedMotion ? 'auto' : 'smooth' });
        lastKey = now;
      }
    });
  }
})();
