/* ==========================================================================
 * plan-detail.js — 历史旅游计划详情（滚动叙事）
 *
 * 职责：
 *   1. 从 URL ?plan=xxx 读取 plan_id，调用 GET /api/travel/plan/{plan_id}
 *   2. 用 marked.js 渲染 markdown
 *   3. 解析出行基本信息（出发地/目的地/天数/人数/偏好）渲染摘要卡片
 *   4. 滚动揭示动画 (IntersectionObserver)
 *   5. 复制 Markdown、打印/导出 PDF
 *   6. 主题切换（与 main.css 设计系统同步）
 * ========================================================================== */
(function () {
  'use strict';

  /* -------------------- 工具函数 -------------------- */
  const $  = (sel, ctx = document) => ctx.querySelector(sel);
  const $$ = (sel, ctx = document) => Array.from(ctx.querySelectorAll(sel));

  const escapeHtml = (s) =>
    String(s ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');

  const formatBytes = (bytes) => {
    if (!bytes && bytes !== 0) return '— KB';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
  };

  const formatDate = (ts) => {
    if (!ts) return '';
    const d = new Date(ts);
    if (isNaN(d.getTime())) return '';
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  };

  /* -------------------- Toast -------------------- */
  let toastTimer = null;
  function toast(msg) {
    const el = $('#toast');
    if (!el) return;
    el.textContent = msg;
    el.classList.add('is-visible');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove('is-visible'), 1800);
  }

  /* -------------------- 主题切换 -------------------- */
  function initTheme() {
    const root = document.documentElement;
    const saved = localStorage.getItem('ai-travel.theme');
    if (saved === 'light' || saved === 'dark') {
      root.setAttribute('data-theme', saved);
    } else {
      root.setAttribute('data-theme', 'auto');
    }
    const btn = $('#themeToggle');
    if (btn) {
      btn.addEventListener('click', () => {
        const current = root.getAttribute('data-theme') ||
          (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
        const next = current === 'dark' ? 'light' : 'dark';
        root.setAttribute('data-theme', next);
        localStorage.setItem('ai-travel.theme', next);
        toast(next === 'dark' ? '已切换到深色主题' : '已切换到浅色主题');
      });
    }
  }

  /* -------------------- 解析 markdown 提取基本信息 -------------------- */
  /**
   * 从 markdown 中提取摘要信息：
   *  - 标题（第一个 H1 / 或 fallback "标题"）
   *  - 出发地 / 目的地 / 天数 / 人数 / 偏好
   * 兼容多种常见格式：
   *  - "> 出发地：北京 / 目的地：上海 / 天数：3 / 人数：2" （后端默认模板）
   *  - "- 出发地：**北京** ..."
   */
  function parseSummary(md, planId) {
    const summary = {
      planId: planId,
      title: '',
      subtitle: '',
      departure: '',
      destination: '',
      days: '',
      nights: '',
      people: '',
      preferences: [],
    };

    if (!md) return summary;

    // 标题：第一个 # 开头的行
    const titleMatch = md.match(/^\s*#\s+(.+?)\s*$/m);
    if (titleMatch) {
      summary.title = titleMatch[1].trim();
    } else {
      summary.title = '未命名行程';
    }

    // 优先匹配引用块 > 出发地 / 目的地 / 天数 / 人数
    const blockquoteRegex = /^\s*>\s*(.+)$/m;
    const blockMatch = md.match(blockquoteRegex);
    if (blockMatch) {
      const line = blockMatch[1];
      const pick = (label) => {
        const re = new RegExp(`${label}[：:]\\s*\\*?\\*?(.+?)\\*?\\*?(?=\\s*(?:\\/|$|\\n))`);
        const m = line.match(re);
        return m ? m[1].trim().replace(/\*+/g, '') : '';
      };
      summary.departure  = pick('出发地');
      summary.destination = pick('目的地');
      summary.days = pick('天数');
      summary.people = pick('人数');
    }

    // fallback：扫描全文找关键 key
    const lookup = (label) => {
      const reList = [
        new RegExp(`-\\s*${label}[：:]\\s*\\*?\\*?(.+?)\\*?\\*?(?=\\s*$)`, 'm'),
        new RegExp(`${label}[：:]\\s*\\*?\\*?(.+?)\\*?\\*?`, 'm'),
      ];
      for (const re of reList) {
        const m = md.match(re);
        if (m) return m[1].trim().replace(/\*+/g, '');
      }
      return '';
    };
    if (!summary.departure)   summary.departure   = lookup('出发地');
    if (!summary.destination) summary.destination = lookup('目的地');
    if (!summary.days)        summary.days        = lookup('天数');
    if (!summary.people)      summary.people      = lookup('人数');

    // 偏好（可多选）
    const prefMatch = md.match(/出行偏好（可多选）[：:]\s*\*?\*?(.+?)\*?\*?/);
    if (prefMatch) {
      const t = prefMatch[1].trim();
      summary.preferences = t
        .split(/[、，,]/)
        .map((s) => s.trim().replace(/\*+/g, ''))
        .filter(Boolean);
    }

    // 天数 -> X 天 Y 晚
    const dayNum = parseInt(summary.days, 10);
    if (!isNaN(dayNum) && dayNum > 0) {
      summary.days = `${dayNum} 天`;
      summary.nights = `${Math.max(0, dayNum - 1)} 晚`;
    }

    // 副标题
    const pieces = [];
    if (summary.departure && summary.destination) {
      pieces.push(`${summary.departure} → ${summary.destination}`);
    } else if (summary.departure || summary.destination) {
      pieces.push(summary.departure || summary.destination);
    }
    if (summary.days) pieces.push(summary.days);
    if (summary.people) pieces.push(summary.people);
    summary.subtitle = pieces.join(' · ') || '一段即将开始的旅程';

    return summary;
  }

  /* -------------------- 渲染摘要卡片 -------------------- */
  function renderSummary(s) {
    const grid = $('#summaryGrid');
    if (!grid) return;

    const cards = [];
    if (s.destination) {
      cards.push({ label: '目的地', value: s.destination, sub: s.departure ? `出发地：${s.departure}` : '' });
    } else if (s.departure) {
      cards.push({ label: '出发地', value: s.departure });
    }
    if (s.days) cards.push({ label: '行程时长', value: s.days, sub: s.nights || '' });
    if (s.people) cards.push({ label: '出行人数', value: s.people, sub: '成人' });
    if (s.preferences.length) {
      cards.push({
        label: '出行偏好',
        value: s.preferences.slice(0, 3).join(' · '),
        sub: s.preferences.length > 3 ? `+${s.preferences.length - 3} 项` : '',
      });
    } else {
      cards.push({ label: '出行偏好', value: '无特殊偏好', sub: '经典通用' });
    }
    cards.push({ label: '行程编号', value: s.planId, sub: 'Markdown 源文件', mono: true });

    grid.innerHTML = cards
      .map(
        (c) => `
        <div class="summary-card">
          <span class="summary-card__label">${escapeHtml(c.label)}</span>
          <span class="summary-card__value" ${c.mono ? 'style="font-family:var(--font-mono);font-size:0.95rem;"' : ''}>${escapeHtml(c.value)}</span>
          ${c.sub ? `<span class="summary-card__sub">${escapeHtml(c.sub)}</span>` : ''}
        </div>`
      )
      .join('');
  }

  /* -------------------- 渲染 Hero -------------------- */
  function renderHero(s) {
    $('#heroTitle').textContent = s.title;
    $('#heroSub').textContent   = s.subtitle;
    $('#heroId').textContent    = s.planId;

    // 尝试从 markdown 时间戳或文件名解析日期
    const stamp = s.planId.match(/(\d{8})/);
    let prettyDate = '';
    if (stamp) {
      const raw = stamp[1]; // YYYYMMDD
      const y = raw.slice(0, 4);
      const m = raw.slice(4, 6);
      const d = raw.slice(6, 8);
      prettyDate = `${y}年${parseInt(m, 10)}月${parseInt(d, 10)}日`;
    }
    $('#heroDate').textContent = prettyDate || '历史行程';
  }

  /* -------------------- 加载计划 -------------------- */
  async function loadPlan() {
    const params = new URLSearchParams(location.search);
    const planId = params.get('plan');

    const loadingStage = $('#loadingStage');
    const errorStage = $('#errorStage');
    const root = $('#detailRoot');

    if (!planId) {
      loadingStage.hidden = true;
      errorStage.hidden = false;
      $('#errorMsg').textContent = '缺少 plan 参数，请通过「我的行程」页面进入。';
      return;
    }

    let payload;
    try {
      const resp = await fetch(`/api/travel/plan/${encodeURIComponent(planId)}`, {
        headers: { Accept: 'application/json' },
      });
      if (!resp.ok) {
        const text = await resp.text().catch(() => '');
        throw new Error(text || `HTTP ${resp.status}`);
      }
      payload = await resp.json();
    } catch (err) {
      console.error('[plan-detail] load failed:', err);
      loadingStage.hidden = true;
      errorStage.hidden = false;
      $('#errorMsg').textContent = `加载失败：${err.message || err}`;
      return;
    }

    const md = payload.markdown || '';
    const summary = parseSummary(md, payload.plan_id || planId);

    // 顶部信息
    renderHero(summary);

    // 摘要卡片
    renderSummary(summary);

    // 渲染 markdown（去除首行 H1，避免与 Hero 标题重复）
    let bodyMd = md;
    if (summary.title && bodyMd.startsWith('#')) {
      bodyMd = bodyMd.replace(/^\s*#\s+.+?\n+/, '');
    }

    if (typeof window.marked === 'function') {
      try {
        window.marked.setOptions({
          breaks: true,
          gfm: true,
          headerIds: true,
          mangle: false,
        });
        const html = window.marked.parse(bodyMd);
        $('#proseRoot').innerHTML = html;
      } catch (e) {
        console.error('[plan-detail] marked error:', e);
        $('#proseRoot').innerHTML = `<pre>${escapeHtml(bodyMd)}</pre>`;
      }
    } else {
      // marked.js 未加载成功，fallback
      $('#proseRoot').innerHTML = `<pre style="white-space:pre-wrap;font-family:var(--font-mono);">${escapeHtml(bodyMd)}</pre>`;
    }

    // 文件元信息
    const sizeText = formatBytes(new Blob([md]).size);
    $('#fileMeta').textContent = `${sizeText} · Markdown`;

    // 切换显示
    loadingStage.hidden = true;
    errorStage.hidden = true;
    root.hidden = false;

    // 触发滚动揭示
    setupReveal();

    // 设置原始 markdown（用于复制）
    setupActions(md);

    // 回到顶部按钮
    setupBackToTop();

    // 锚点：进入页面时滚到顶部
    requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: 'auto' }));
  }

  /* -------------------- 操作按钮 -------------------- */
  function setupActions(md) {
    const copyBtn = $('#copyBtn');
    const printBtn = $('#printBtn');

    if (copyBtn) {
      copyBtn.addEventListener('click', async () => {
        try {
          if (navigator.clipboard && window.isSecureContext) {
            await navigator.clipboard.writeText(md);
          } else {
            // fallback
            const ta = document.createElement('textarea');
            ta.value = md;
            ta.setAttribute('readonly', '');
            ta.style.position = 'absolute';
            ta.style.left = '-9999px';
            document.body.appendChild(ta);
            ta.select();
            document.execCommand('copy');
            document.body.removeChild(ta);
          }
          toast('已复制 Markdown 到剪贴板');
        } catch (e) {
          console.error(e);
          toast('复制失败，请手动选择');
        }
      });
    }

    if (printBtn) {
      printBtn.addEventListener('click', () => {
        // 触发浏览器打印（用户可保存为 PDF）
        window.print();
      });
    }
  }

  /* -------------------- 滚动揭示 -------------------- */
  function setupReveal() {
    const targets = $$('.reveal');
    if (!('IntersectionObserver' in window) || !targets.length) {
      targets.forEach((el) => el.classList.add('is-visible'));
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible');
            io.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: '0px 0px -8% 0px' }
    );
    targets.forEach((el) => io.observe(el));
  }

  /* -------------------- 回到顶部 -------------------- */
  function setupBackToTop() {
    const btn = $('#toTop');
    if (!btn) return;
    const onScroll = () => {
      if (window.scrollY > 600) {
        btn.hidden = false;
        requestAnimationFrame(() => btn.classList.add('is-visible'));
      } else {
        btn.classList.remove('is-visible');
        setTimeout(() => { if (window.scrollY <= 600) btn.hidden = true; }, 320);
      }
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    btn.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));
    onScroll();
  }

  /* -------------------- 启动 -------------------- */
  function init() {
    initTheme();
    // 等 marked.js 加载完成（defer 顺序）
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', loadPlan);
    } else {
      loadPlan();
    }
  }

  init();
})();