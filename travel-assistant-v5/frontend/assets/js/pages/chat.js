/* chat.html 页面脚本 — 流式 SSE + 思考过程 */
document.addEventListener('DOMContentLoaded', async () => {
  const $ = (id) => document.getElementById(id);
  const wrap = $('stream-wrap');
  const stream = $('stream');
  const placeholder = $('placeholder');
  const input = $('input');
  const sendBtn = $('send');

  let history = [];
  let busy = false;

  // 顶部信息
  try {
    const cfg = await App.loadServerConfig();
    const model = cfg?.llm?.model || '未配置';
    $('model-tag').textContent = `🤖 ${model}`;
    $('tools-tag').textContent = cfg?.amap?.api_key ? '🗺️ 高德 MCP 已就绪 · 9 个工具' : '⚠️ 未配置高德 API Key';
  } catch (e) {
    $('model-tag').textContent = '⚠️ 加载失败';
  }

  // 建议 chip
  document.querySelectorAll('.suggest-chip').forEach((el) => {
    el.addEventListener('click', () => {
      input.value = el.dataset.q;
      onSend();
    });
  });

  // 自动撑高
  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 180) + 'px';
  });

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  });
  sendBtn.addEventListener('click', onSend);

  $('new-chat').addEventListener('click', () => {
    if (busy) return;
    history = [];
    stream.innerHTML = '';
    stream.style.display = 'none';
    placeholder.style.display = 'block';
  });

  function ensureStream() {
    if (stream.style.display === 'none') {
      placeholder.style.display = 'none';
      stream.style.display = 'flex';
    }
  }

  function appendUser(text) {
    ensureStream();
    const el = document.createElement('div');
    el.className = 'chat-msg chat-msg--user md-body';
    el.innerHTML = App.renderMarkdown(text);
    stream.appendChild(el);
    wrap.scrollTop = wrap.scrollHeight;
  }

  // 助手消息容器：内部可以塞一个折叠的「思考」面板 + 工具卡片 + 正文
  function appendAssistantShell() {
    ensureStream();
    const el = document.createElement('div');
    el.className = 'chat-msg chat-msg--assistant md-body';
    el.innerHTML = `
      <div class="assistant-thinking" data-role="thinking"></div>
      <div class="assistant-tools"></div>
      <div class="assistant-content"></div>
    `;
    stream.appendChild(el);
    wrap.scrollTop = wrap.scrollHeight;
    return {
      root: el,
      thinking: el.querySelector('.assistant-thinking'),
      toolsBox: el.querySelector('.assistant-tools'),
      contentBox: el.querySelector('.assistant-content'),
    };
  }

  // 思考过程面板（折叠/展开）
  let thinkingAcc = '';
  function ensureThinkingPanel(parts) {
    parts.thinking.innerHTML = '';
    if (!parts.thinking._box) {
      const box = document.createElement('div');
      box.className = 'thinking is-open';
      box.innerHTML = `
        <div class="thinking__head">
          <span class="thinking__label">🧠 模型思考中…（可点击折叠）</span>
        </div>
        <div class="thinking__body"></div>
      `;
      box.querySelector('.thinking__head').addEventListener('click', () => {
        box.classList.toggle('is-open');
      });
      parts.thinking.appendChild(box);
      parts.thinking._box = box;
      parts.thinking._body = box.querySelector('.thinking__body');
    }
    return parts.thinking._box;
  }

  function appendThinking(parts, delta) {
    thinkingAcc += delta || '';
    const box = ensureThinkingPanel(parts);
    box.querySelector('.thinking__label').textContent = '🧠 模型思考过程（点击折叠）';
    box.querySelector('.thinking__head').appendChild(
      Object.assign(document.createElement('span'), { className: 'thinking__pulse' })
    );
    parts.thinking._body.textContent = thinkingAcc;
    wrap.scrollTop = wrap.scrollHeight;
  }

  function removeThinkingPulse(parts) {
    const box = parts.thinking && parts.thinking._box;
    if (!box) return;
    const lbl = box.querySelector('.thinking__label');
    if (lbl) lbl.textContent = '🧠 模型思考过程';
    const pulse = box.querySelector('.thinking__pulse');
    if (pulse) pulse.remove();
  }

  function appendToolCard(parts, name, args, status = 'running') {
    const el = document.createElement('div');
    el.className = 'chat-msg chat-msg--tool';
    el.dataset.tool = name;
    el.innerHTML = `
      <div class="chat-msg__name">
        ${status === 'running' ? '<span class="spinner"></span>' : '✓ '}
        调用工具：${App.escapeHtml(name)}
      </div>
      <div class="chat-msg__args">${App.escapeHtml(JSON.stringify(args || {}, null, 0))}</div>
      <div class="chat-msg__summary" style="${status === 'running' ? 'display:none;' : ''}"></div>
    `;
    parts.toolsBox.appendChild(el);
    wrap.scrollTop = wrap.scrollHeight;
    return el;
  }

  function updateToolCard(card, name, args, summary) {
    card.innerHTML = `
      <div class="chat-msg__name">✓ 调用工具：${App.escapeHtml(name)}</div>
      <div class="chat-msg__args">${App.escapeHtml(JSON.stringify(args || {}, null, 0))}</div>
      <div class="chat-msg__summary">${App.renderMarkdown(summary || '')}</div>
    `;
    wrap.scrollTop = wrap.scrollHeight;
  }

  async function onSend() {
    if (busy) return;
    const text = input.value.trim();
    if (!text) return;
    input.value = '';
    input.style.height = 'auto';

    appendUser(text);
    const parts = appendAssistantShell();
    thinkingAcc = '';
    parts.contentBox.innerHTML = '<span class="muted"><span class="spinner"></span> 思考中…</span>';
    busy = true;
    sendBtn.disabled = true;

    try {
      const r = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, history }),
      });
      if (!r.ok || !r.body) {
        const t = await r.text();
        parts.contentBox.innerHTML = `<span style="color: var(--danger);">请求失败：${App.escapeHtml(t)}</span>`;
        busy = false; sendBtn.disabled = false;
        return;
      }

      const reader = r.body.getReader();
      const dec = new TextDecoder();
      let buffer = '';
      let accContent = '';
      const toolCards = new Map();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += dec.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';
        for (const ev of lines) {
          const line = ev.trim();
          if (!line.startsWith('data:')) continue;
          const data = line.replace(/^data:\s*/, '');
          if (!data) continue;
          let obj;
          try { obj = JSON.parse(data); } catch (e) { continue; }
          if (obj.event === 'thinking') {
            appendThinking(parts, obj.delta || '');
          } else if (obj.event === 'tool') {
            const key = (obj.name || '') + JSON.stringify(obj.arguments || {});
            if (obj.status === 'running') {
              const c = appendToolCard(parts, obj.name, obj.arguments, 'running');
              toolCards.set(key, c);
            } else if (obj.status === 'done') {
              let card = toolCards.get(key);
              if (!card) card = appendToolCard(parts, obj.name, obj.arguments, 'running');
              updateToolCard(card, obj.name, obj.arguments, obj.summary);
            }
          } else if (obj.event === 'content') {
            // 一旦开始正文，就关闭思考面板的红点
            removeThinkingPulse(parts);
            accContent += obj.delta || '';
            parts.contentBox.innerHTML = App.renderMarkdown(accContent);
            wrap.scrollTop = wrap.scrollHeight;
          } else if (obj.event === 'done') {
            removeThinkingPulse(parts);
            if (obj.error) {
              parts.contentBox.innerHTML = `<span style="color: var(--danger);">出错：${App.escapeHtml(obj.error)}</span>`;
            } else if (!accContent && (!obj.tools_used || !obj.tools_used.length) && !thinkingAcc) {
              parts.contentBox.innerHTML = '<span class="muted">（未返回内容）</span>';
            }
            // 兼容：服务端兜底提供了完整 reasoning 字段（流式漏发）
            if (obj.reasoning && !thinkingAcc) {
              thinkingAcc = obj.reasoning;
              appendThinking(parts, obj.reasoning);
              removeThinkingPulse(parts);
            }
          }
        }
      }

      // 智能收尾
      // 关闭思考面板的红点
      removeThinkingPulse(parts);

      history.push({ role: 'user', content: text });
      if (accContent) history.push({ role: 'assistant', content: accContent });
      if (history.length > 20) history = history.slice(-20);
    } catch (e) {
      parts.contentBox.innerHTML = `<span style="color: var(--danger);">出错：${App.escapeHtml(e.message)}</span>`;
    } finally {
      busy = false;
      sendBtn.disabled = false;
      input.focus();
    }
  }

  input.focus();
});
