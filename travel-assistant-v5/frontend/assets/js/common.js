/* ==========================================================================
   common.js — 全局工具 / 主题 / 滚动监听
   依赖：marked.js (CDN)
   ========================================================================== */

const App = (() => {
  const $ = (sel, el = document) => el.querySelector(sel);
  const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));

  // ---------- base URL / API ----------
  const apiBase = (() => {
    // 留作 override 入口（如果前后端同源，直接用空串即可）
    return window.__API_BASE__ || '';
  })();

  async function api(path, options = {}) {
    const url = apiBase + path;
    const opts = Object.assign({ headers: {} }, options);
    if (opts.body && typeof opts.body === 'object' && !(opts.body instanceof FormData)) {
      opts.body = JSON.stringify(opts.body);
      opts.headers['Content-Type'] = 'application/json';
    }
    let r;
    try {
      r = await fetch(url, opts);
    } catch (e) {
      throw new Error('网络错误：' + e.message);
    }
    if (!r.ok) {
      let msg = r.statusText;
      try {
        const j = await r.json();
        msg = j.error || j.detail || JSON.stringify(j);
      } catch (_) {}
      throw new Error(msg);
    }
    const ct = r.headers.get('content-type') || '';
    if (ct.includes('application/json')) return r.json();
    return r.text();
  }

  // ---------- marked ----------
  let md = null;
  function getMarked() {
    if (md) return md;
    if (typeof window.marked === 'undefined') {
      console.warn('marked.js 未加载');
      return { parse: (s) => `<pre>${escapeHtml(s)}</pre>` };
    }
    md = window.marked;
    md.setOptions({
      gfm: true,
      breaks: true,
      headerIds: false,
      mangle: false,
    });
    return md;
  }

  function renderMarkdown(text) {
    if (!text) return '';
    return getMarked().parse(text);
  }

  function escapeHtml(s) {
    return String(s || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // ---------- toast ----------
  function toast(msg, type = 'info', duration = 2400) {
    let layer = document.getElementById('toast-layer');
    if (!layer) {
      layer = document.createElement('div');
      layer.id = 'toast-layer';
      Object.assign(layer.style, {
        position: 'fixed', top: '24px', right: '24px', zIndex: 9999,
        display: 'flex', flexDirection: 'column', gap: '10px', pointerEvents: 'none',
      });
      document.body.appendChild(layer);
    }
    const t = document.createElement('div');
    t.textContent = msg;
    Object.assign(t.style, {
      background: 'rgba(34,34,34,.92)', color: '#fff',
      padding: '10px 16px', borderRadius: '10px', fontSize: '14px',
      boxShadow: '0 6px 24px rgba(0,0,0,.18)', opacity: '0',
      transform: 'translateY(-8px)', transition: 'all 320ms cubic-bezier(.16,.84,.44,1)',
      maxWidth: '360px',
    });
    if (type === 'success') t.style.background = 'rgba(47,138,91,.95)';
    if (type === 'error') t.style.background = 'rgba(200,66,60,.95)';
    layer.appendChild(t);
    requestAnimationFrame(() => {
      t.style.opacity = '1';
      t.style.transform = 'translateY(0)';
    });
    setTimeout(() => {
      t.style.opacity = '0';
      setTimeout(() => t.remove(), 320);
    }, duration);
  }

  // ---------- theme ----------
  function applyTheme(theme) {
    // theme: 'light' | 'dark' | 'auto'
    const root = document.documentElement;
    if (theme === 'auto') {
      root.removeAttribute('data-theme');
    } else {
      root.setAttribute('data-theme', theme);
    }
    localStorage.setItem('theme', theme);
  }

  function initTheme() {
    const saved = localStorage.getItem('theme') || 'auto';
    applyTheme(saved);
  }

  function bindThemeToggle(btnId = 'theme-toggle') {
    const btn = document.getElementById(btnId);
    if (!btn) return;
    btn.addEventListener('click', () => {
      const cur = localStorage.getItem('theme') || 'auto';
      const next = cur === 'dark' ? 'light' : cur === 'light' ? 'auto' : 'dark';
      applyTheme(next);
      toast('主题：' + (next === 'auto' ? '跟随系统' : next === 'dark' ? '深色' : '浅色'));
    });
  }

  // ---------- top nav 滚动效果 ----------
  function bindTopnav() {
    const nav = document.querySelector('.topnav');
    if (!nav) return;
    const onScroll = () => {
      if (window.scrollY > 12) nav.classList.add('is-scrolled');
      else nav.classList.remove('is-scrolled');
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }

  // ---------- IntersectionObserver reveal ----------
  function bindReveal() {
    const els = $$('.reveal');
    if (!('IntersectionObserver' in window)) {
      els.forEach((el) => el.classList.add('is-visible'));
      return;
    }
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) {
        if (e.isIntersecting) {
          e.target.classList.add('is-visible');
          io.unobserve(e.target);
        }
      }
    }, { threshold: 0.12, rootMargin: '0px 0px -10% 0px' });
    els.forEach((el) => io.observe(el));
  }

  // ---------- scroll progress ----------
  function bindScrollProgress(id = 'scroll-progress') {
    const bar = document.getElementById(id);
    if (!bar) return;
    const onScroll = () => {
      const h = document.documentElement;
      const max = h.scrollHeight - h.clientHeight;
      const pct = max > 0 ? (h.scrollTop / max) * 100 : 0;
      bar.style.width = pct + '%';
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }

  // ---------- 复制 ----------
  async function copy(text) {
    try {
      await navigator.clipboard.writeText(text);
      toast('已复制到剪贴板', 'success');
    } catch (e) {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand('copy'); toast('已复制到剪贴板', 'success'); }
      catch (e) { toast('复制失败', 'error'); }
      ta.remove();
    }
  }

  // ---------- 渲染 Markdown 到容器 ----------
  function render(targetEl, md) {
    targetEl.innerHTML = renderMarkdown(md);
    targetEl.classList.add('md-body');
  }

  // ---------- saved config ----------
  async function loadServerConfig() {
    return api('/api/config');
  }

  async function saveServerConfig(cfg) {
    return api('/api/config', { method: 'POST', body: cfg });
  }

  // ---------- 启动 ----------
  function boot() {
    initTheme();
    bindThemeToggle();
    bindTopnav();
    bindReveal();
    bindScrollProgress();
  }

  document.addEventListener('DOMContentLoaded', boot);

  return {
    $, $$, api, renderMarkdown, render, copy, toast, escapeHtml,
    applyTheme, initTheme,
    loadServerConfig, saveServerConfig,
  };
})();
window.App = App;
