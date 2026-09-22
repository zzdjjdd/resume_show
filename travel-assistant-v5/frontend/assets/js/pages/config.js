/* config.html 页面脚本 */
document.addEventListener('DOMContentLoaded', async () => {
  // 加密切换可见
  function bindToggle(btnId, inputId) {
    const btn = document.getElementById(btnId);
    const inp = document.getElementById(inputId);
    if (!btn || !inp) return;
    btn.addEventListener('click', () => {
      const isPwd = inp.type === 'password';
      inp.type = isPwd ? 'text' : 'password';
      btn.textContent = isPwd ? '隐藏' : '显示';
    });
  }
  bindToggle('toggle-llm-key', 'llm-key');
  bindToggle('toggle-amap-key', 'amap-key');

  // 加载
  let cfg = {};
  try {
    cfg = await App.loadServerConfig();
  } catch (e) {
    App.toast('加载配置失败：' + e.message, 'error');
  }
  document.getElementById('llm-key').value = cfg.llm?.api_key || '';
  document.getElementById('llm-url').value = cfg.llm?.base_url || 'https://api.openai.com/v1';
  document.getElementById('llm-model-input').value = cfg.llm?.model || 'gpt-4o-mini';
  document.getElementById('llm-timeout').value = cfg.llm?.timeout || 60;
  document.getElementById('amap-key').value = cfg.amap?.api_key || '';
  document.getElementById('amap-sse').value = cfg.amap?.sse_url || '';
  document.getElementById('mcp-url').value = cfg.mcp?.server_url || '';
  document.getElementById('mcp-timeout').value = cfg.mcp?.timeout || 30;
  document.getElementById('mcp-enabled').checked = !!cfg.mcp?.enabled;
  document.getElementById('mcp2-url').value = cfg.mcp2?.server_url || '';
  document.getElementById('mcp2-timeout').value = cfg.mcp2?.timeout || 30;
  document.getElementById('mcp2-enabled').checked = !!cfg.mcp2?.enabled;
  document.getElementById('theme').value = localStorage.getItem('theme') || 'auto';

  // 测试 LLM
  document.getElementById('test-llm').addEventListener('click', async () => {
    const st = document.getElementById('llm-status');
    const btn = document.getElementById('test-llm');
    btn.disabled = true;
    st.innerHTML = '<span class="spinner"></span> 测试中…';
    try {
      const r = await App.api('/api/test/llm', {
        method: 'POST',
        body: {
          api_key: document.getElementById('llm-key').value,
          base_url: document.getElementById('llm-url').value,
          model: document.getElementById('llm-model-input').value,
          timeout: parseInt(document.getElementById('llm-timeout').value, 10),
        },
      });
      if (r.ok) {
        st.innerHTML = `<span style="color: var(--success);">✓ 连接成功，可用模型 ${r.models_count} 个</span>`;
        App.toast('LLM 连接成功', 'success');
      } else {
        st.innerHTML = `<span style="color: var(--danger);">✗ ${App.escapeHtml(r.error || '失败')}</span>`;
      }
    } catch (e) {
      st.innerHTML = `<span style="color: var(--danger);">✗ ${App.escapeHtml(e.message)}</span>`;
    } finally {
      btn.disabled = false;
    }
  });

  // 测试高德
  document.getElementById('test-amap').addEventListener('click', async () => {
    const st = document.getElementById('amap-status');
    const btn = document.getElementById('test-amap');
    btn.disabled = true;
    st.innerHTML = '<span class="spinner"></span> 测试中…';
    try {
      const r = await App.api('/api/test/amap', {
        method: 'POST',
        body: { api_key: document.getElementById('amap-key').value },
      });
      if (r.ok) {
        st.innerHTML = '<span style="color: var(--success);">✓ 高德 API Key 有效</span>';
        App.toast('高德连接成功', 'success');
      } else {
        st.innerHTML = `<span style="color: var(--danger);">✗ ${App.escapeHtml(r.error || '失败')}</span>`;
      }
    } catch (e) {
      st.innerHTML = `<span style="color: var(--danger);">✗ ${App.escapeHtml(e.message)}</span>`;
    } finally {
      btn.disabled = false;
    }
  });

  // 获取模型列表
  async function refreshModels() {
    const sel = document.getElementById('llm-model');
    sel.innerHTML = '<option value="">加载中…</option>';
    try {
      const r = await App.api('/api/llm/models', {
        method: 'POST',
        body: {
          api_key: document.getElementById('llm-key').value,
          base_url: document.getElementById('llm-url').value,
          model: document.getElementById('llm-model-input').value,
        },
      });
      if (r.models && r.models.length) {
        sel.innerHTML = r.models.map((m) => `<option value="${App.escapeHtml(m.id)}">${App.escapeHtml(m.id)}</option>`).join('');
        // 选中当前 model
        const cur = document.getElementById('llm-model-input').value;
        const exist = Array.from(sel.options).find((o) => o.value === cur);
        if (exist) sel.value = cur;
      } else {
        sel.innerHTML = '<option value="">未拉取到模型，可手动输入</option>';
      }
    } catch (e) {
      sel.innerHTML = `<option value="">${App.escapeHtml(e.message)}</option>`;
    }
  }
  document.getElementById('refresh-models').addEventListener('click', refreshModels);

  // 选中下拉 → 同步到 input
  document.getElementById('llm-model').addEventListener('change', (e) => {
    if (e.target.value) document.getElementById('llm-model-input').value = e.target.value;
  });

  // 保存 LLM
  document.getElementById('save-llm').addEventListener('click', async () => {
    const st = document.getElementById('llm-status');
    try {
      await App.api('/api/config/llm', {
        method: 'POST',
        body: {
          api_key: document.getElementById('llm-key').value,
          base_url: document.getElementById('llm-url').value,
          model: document.getElementById('llm-model-input').value,
          timeout: parseInt(document.getElementById('llm-timeout').value, 10),
        },
      });
      st.innerHTML = '<span style="color: var(--success);">✓ 已保存</span>';
      App.toast('LLM 配置已保存', 'success');
    } catch (e) {
      st.innerHTML = `<span style="color: var(--danger);">✗ ${App.escapeHtml(e.message)}</span>`;
    }
  });

  // 保存 高德
  document.getElementById('save-amap').addEventListener('click', async () => {
    const st = document.getElementById('amap-status');
    try {
      await App.api('/api/config/amap', {
        method: 'POST',
        body: {
          api_key: document.getElementById('amap-key').value,
          sse_url: document.getElementById('amap-sse').value,
        },
      });
      st.innerHTML = '<span style="color: var(--success);">✓ 已保存</span>';
      App.toast('高德配置已保存', 'success');
    } catch (e) {
      st.innerHTML = `<span style="color: var(--danger);">✗ ${App.escapeHtml(e.message)}</span>`;
    }
  });

  // 主题切换
  document.getElementById('theme').addEventListener('change', (e) => {
    App.applyTheme(e.target.value);
    App.toast('主题：' + (e.target.value === 'auto' ? '跟随系统' : e.target.value === 'dark' ? '深色' : '浅色'));
  });

  // ---------- MCP ----------
  // prefix: 'mcp'(服务 1) 或 'mcp2'(服务 2)
  async function readMcpForm(prefix = 'mcp') {
    return {
      server_url: document.getElementById(prefix + '-url').value.trim(),
      timeout: parseInt(document.getElementById(prefix + '-timeout').value, 10) || 30,
      enabled: document.getElementById(prefix + '-enabled').checked,
    };
  }
  function renderMcpTools(tools, prefix = 'mcp') {
    const box = document.getElementById(prefix + '-tools-box');
    const list = document.getElementById(prefix + '-tools-list');
    const count = document.getElementById(prefix + '-tools-count');
    if (!tools || !tools.length) {
      box.style.display = 'none';
      return;
    }
    box.style.display = 'block';
    count.textContent = tools.length;
    list.innerHTML = tools.map((t) => {
      const fn = t.function || {};
      const name = fn.name || '?';
      return `<span class="tag accent" title="${App.escapeHtml(fn.description || '')}">mc_${App.escapeHtml(name)}</span>`;
    }).join('');
  }

  // 测试 MCP
  document.getElementById('test-mcp').addEventListener('click', async () => {
    const st = document.getElementById('mcp-status');
    const btn = document.getElementById('test-mcp');
    btn.disabled = true;
    st.innerHTML = '<span class="spinner"></span> 测试中…';
    try {
      const form = await readMcpForm();
      const r = await App.api('/api/test/mcp', {
        method: 'POST',
        body: { server_url: form.server_url, timeout: form.timeout },
      });
      if (r.ok) {
        st.innerHTML = `<span style="color: var(--success);">✓ 已加载 ${r.tools_count} 个工具</span>`;
        App.toast(`MCP 连接成功 · ${r.tools_count} 个工具`, 'success');
        // 注:测试时不会写回 app.state,需要用户点"保存"才会真正启用
        renderMcpTools((r.tools_preview || []).map((n) => ({ function: { name: n } })));
      } else {
        st.innerHTML = `<span style="color: var(--danger);">✗ ${App.escapeHtml(r.error || '失败')}</span>`;
        document.getElementById('mcp-tools-box').style.display = 'none';
      }
    } catch (e) {
      st.innerHTML = `<span style="color: var(--danger);">✗ ${App.escapeHtml(e.message)}</span>`;
    } finally {
      btn.disabled = false;
    }
  });

  // 刷新工具列表(必须已启用)
  document.getElementById('refresh-mcp').addEventListener('click', async () => {
    const st = document.getElementById('mcp-status');
    const btn = document.getElementById('refresh-mcp');
    btn.disabled = true;
    st.innerHTML = '<span class="spinner"></span> 重新加载中…';
    try {
      const r = await App.api('/api/mcp/refresh', { method: 'POST' });
      if (r.ok) {
        st.innerHTML = `<span style="color: var(--success);">✓ 已刷新,共 ${r.tools.length} 个工具</span>`;
        renderMcpTools(r.tools);
        App.toast('MCP 工具列表已刷新', 'success');
      } else {
        st.innerHTML = `<span style="color: var(--danger);">✗ ${App.escapeHtml(r.error || '失败')}</span>`;
      }
    } catch (e) {
      st.innerHTML = `<span style="color: var(--danger);">✗ ${App.escapeHtml(e.message)}</span>`;
    } finally {
      btn.disabled = false;
    }
  });

  // 保存 MCP
  document.getElementById('save-mcp').addEventListener('click', async () => {
    const st = document.getElementById('mcp-status');
    try {
      const form = await readMcpForm();
      await App.api('/api/config/mcp', { method: 'POST', body: form });
      st.innerHTML = '<span style="color: var(--success);">✓ 已保存(需重启服务生效)</span>';
      App.toast('MCP 配置已保存', 'success');
    } catch (e) {
      st.innerHTML = `<span style="color: var(--danger);">✗ ${App.escapeHtml(e.message)}</span>`;
    }
  });

  // ---------- MCP 服务 2 ----------
  // 测试 MCP 2(复用 /api/test/mcp,传入服务 2 的 server_url)
  document.getElementById('test-mcp2').addEventListener('click', async () => {
    const st = document.getElementById('mcp2-status');
    const btn = document.getElementById('test-mcp2');
    btn.disabled = true;
    st.innerHTML = '<span class="spinner"></span> 测试中…';
    try {
      const form = await readMcpForm('mcp2');
      const r = await App.api('/api/test/mcp', {
        method: 'POST',
        body: { server_url: form.server_url, timeout: form.timeout },
      });
      if (r.ok) {
        st.innerHTML = `<span style="color: var(--success);">✓ 已加载 ${r.tools_count} 个工具</span>`;
        App.toast(`MCP 2 连接成功 · ${r.tools_count} 个工具`, 'success');
        renderMcpTools((r.tools_preview || []).map((n) => ({ function: { name: n } })), 'mcp2');
      } else {
        st.innerHTML = `<span style="color: var(--danger);">✗ ${App.escapeHtml(r.error || '失败')}</span>`;
        document.getElementById('mcp2-tools-box').style.display = 'none';
      }
    } catch (e) {
      st.innerHTML = `<span style="color: var(--danger);">✗ ${App.escapeHtml(e.message)}</span>`;
    } finally {
      btn.disabled = false;
    }
  });

  // 保存 MCP 2
  document.getElementById('save-mcp2').addEventListener('click', async () => {
    const st = document.getElementById('mcp2-status');
    try {
      const form = await readMcpForm('mcp2');
      await App.api('/api/config/mcp2', { method: 'POST', body: form });
      st.innerHTML = '<span style="color: var(--success);">✓ 已保存</span>';
      App.toast('MCP 2 配置已保存', 'success');
    } catch (e) {
      st.innerHTML = `<span style="color: var(--danger);">✗ ${App.escapeHtml(e.message)}</span>`;
    }
  });

  // 启动时若已加载 MCP 工具,展示
  try {
    const r = await App.api('/api/mcp/tools');
    if (r.ok && r.tools && r.tools.length) {
      renderMcpTools(r.tools);
    }
  } catch (e) {
    // 静默:启动时获取失败不打扰
  }

  // 保存全部
  document.getElementById('save-all').addEventListener('click', async () => {
    const st = document.getElementById('all-status');
    try {
      const mcpForm = await readMcpForm();
      const mcp2Form = await readMcpForm('mcp2');
      await App.saveServerConfig({
        llm: {
          api_key: document.getElementById('llm-key').value,
          base_url: document.getElementById('llm-url').value,
          model: document.getElementById('llm-model-input').value,
          timeout: parseInt(document.getElementById('llm-timeout').value, 10),
        },
        amap: {
          api_key: document.getElementById('amap-key').value,
          sse_url: document.getElementById('amap-sse').value,
        },
        mcp: mcpForm,
        mcp2: mcp2Form,
        ui: { theme: document.getElementById('theme').value },
      });
      st.innerHTML = '<span style="color: var(--success);">✓ 全部已保存</span>';
      App.toast('全部配置已保存', 'success');
    } catch (e) {
      st.innerHTML = `<span style="color: var(--danger);">✗ ${App.escapeHtml(e.message)}</span>`;
    }
  });

  // 自动尝试获取模型
  if (document.getElementById('llm-key').value) {
    refreshModels();
  }
});
