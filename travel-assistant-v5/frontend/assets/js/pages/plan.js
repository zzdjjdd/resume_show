/* plan.html 页面脚本 */
document.addEventListener('DOMContentLoaded', () => {
  const $ = (id) => document.getElementById(id);

  // 步进器
  function stepper(minusId, plusId, inputId, min = 1, max = 99) {
    const inp = $(inputId);
    $(minusId).addEventListener('click', () => {
      inp.value = Math.max(min, parseInt(inp.value || '1', 10) - 1);
    });
    $(plusId).addEventListener('click', () => {
      inp.value = Math.min(max, parseInt(inp.value || '1', 10) + 1);
    });
  }
  stepper('days-minus', 'days-plus', 'days', 1, 14);
  stepper('ppl-minus', 'ppl-plus', 'people', 1, 20);

  // 偏好多选
  document.querySelectorAll('.pref').forEach((el) => {
    el.addEventListener('click', () => {
      el.classList.toggle('is-active');
    });
  });

  // 生成
  $('generate').addEventListener('click', async () => {
    const departure = $('departure').value.trim();
    const destination = $('destination').value.trim();
    const days = parseInt($('days').value, 10) || 1;
    const people = parseInt($('people').value, 10) || 1;
    const additional = $('additional').value.trim();
    const preferences = Array.from(document.querySelectorAll('.pref.is-active')).map((el) => el.dataset.val);

    if (!departure || !destination) {
      App.toast('请填写出发地和目的地', 'error');
      return;
    }

    const out = $('output');
    const status = $('status');
    const btn = $('generate');
    btn.disabled = true;
    status.innerHTML = '<span class="spinner"></span> AI 正在编排行程…';

    out.innerHTML = '<div class="loading-block"><span class="spinner"></span> 正在综合偏好、地理与时间数据生成行程…</div>';
    $('output-actions').style.display = 'none';

    try {
      const r = await App.api('/api/travel/plan', {
        method: 'POST',
        body: { departure, destination, days, people, preferences, additional },
      });
      if (!r.ok) throw new Error(r.error || '生成失败');

      App.render(out, r.markdown);
      status.innerHTML = `<span style="color: var(--success);">✓ 已生成（plan_id: ${r.plan_id}）</span>`;
      $('output-actions').style.display = 'flex';

      // 绑定按钮
      $('copy-md').onclick = () => App.copy(r.markdown);
      $('download-md').onclick = () => {
        const blob = new Blob([r.markdown], { type: 'text/markdown;charset=utf-8' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `${r.plan_id}.md`;
        a.click();
        URL.revokeObjectURL(a.href);
      };
      $('view-detail').onclick = () => window.open(`/plan-detail?plan=${r.plan_id}`, '_blank');

      // 刷新历史并选中刚生成的
      await loadHistory({ selectPlanId: r.plan_id });
      App.toast('行程已生成', 'success');
    } catch (e) {
      out.innerHTML = `<div class="card" style="border-color: var(--danger);"><strong style="color: var(--danger);">生成失败</strong><br/><span style="font-family: var(--font-mono); font-size: 12px;">${App.escapeHtml(e.message)}</span></div>`;
      status.innerHTML = `<span style="color: var(--danger);">✗ ${App.escapeHtml(e.message)}</span>`;
    } finally {
      btn.disabled = false;
    }
  });

  // ---------- 历史计划（左列表 + 右预览） ----------
  let historyData = [];
  let currentPreviewId = null;

  async function loadHistory({ selectPlanId = null } = {}) {
    const listEl = $('history-list');
    const countEl = $('history-count');
    try {
      const r = await App.api('/api/travel/plans');
      historyData = r.plans || [];
      if (!historyData.length) {
        listEl.innerHTML = '<div class="history-empty muted">— 暂无历史记录 —</div>';
        countEl.textContent = '0 条';
        $('history-preview').innerHTML = '<div class="history-empty muted">生成第一个行程后即可在左侧查阅历史。</div>';
        return;
      }
      countEl.textContent = `共 ${historyData.length} 条`;
      listEl.innerHTML = historyData.map((p) => {
        const dt = new Date(p.modified * 1000).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
        return `
          <button class="history-item" data-id="${App.escapeHtml(p.plan_id)}" type="button">
            <span class="history-item__title">${App.escapeHtml(p.plan_id)}</span>
            <span class="history-item__meta">${App.escapeHtml(dt)} · ${(p.size / 1024).toFixed(1)} KB</span>
          </button>
        `;
      }).join('');
      listEl.querySelectorAll('.history-item').forEach((btn) => {
        btn.addEventListener('click', () => selectPreview(btn.dataset.id));
      });

      // 默认选中
      const target = selectPlanId
        || (currentPreviewId && historyData.find((p) => p.plan_id === currentPreviewId)?.plan_id)
        || historyData[0].plan_id;
      selectPreview(target);
    } catch (e) {
      listEl.innerHTML = `<div class="history-empty" style="color: var(--danger);">加载失败：${App.escapeHtml(e.message)}</div>`;
    }
  }

  async function selectPreview(planId) {
    if (!planId) return;
    currentPreviewId = planId;
    const listEl = $('history-list');
    listEl.querySelectorAll('.history-item').forEach((b) => {
      b.classList.toggle('is-active', b.dataset.id === planId);
    });
    const preview = $('history-preview');
    preview.innerHTML = '<div class="history-empty"><span class="spinner"></span> 加载中…</div>';

    try {
      const r = await App.api('/api/travel/plan/' + encodeURIComponent(planId));
      preview.innerHTML = `
        <div class="history-toolbar">
          <span class="history-toolbar__title">${App.escapeHtml(planId)}</span>
          <button class="btn btn--icon" id="hp-copy" title="复制 Markdown">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>
          </button>
          <button class="btn btn--icon" id="hp-dl" title="下载 .md">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
          </button>
          <a class="btn btn--icon" href="/plan-detail?plan=${encodeURIComponent(planId)}" target="_blank" title="新窗口打开">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14L21 3"/></svg>
          </a>
        </div>
        <article class="md-body" id="hp-body"></article>
      `;
      App.render(document.getElementById('hp-body'), r.markdown);
      document.getElementById('hp-copy').onclick = () => App.copy(r.markdown);
      document.getElementById('hp-dl').onclick = () => {
        const blob = new Blob([r.markdown], { type: 'text/markdown;charset=utf-8' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `${planId}.md`;
        a.click();
        URL.revokeObjectURL(a.href);
      };
    } catch (e) {
      preview.innerHTML = `<div class="history-empty" style="color: var(--danger);">加载失败：${App.escapeHtml(e.message)}</div>`;
    }
  }

  loadHistory();
});
