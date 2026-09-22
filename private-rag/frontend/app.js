// ===== RAG 前端 · 现代深色科技感 =====
const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

const state = {
  history: [],          // 多轮对话历史
  lastCitations: [],    // 最近一次回答的引用
  typingTimer: null,    // 打字机定时器
};

// ---------- Tab 切换 ----------
$$('.nav-item').forEach(btn => {
  btn.addEventListener('click', () => {
    $$('.nav-item').forEach(b => b.classList.remove('active'));
    $$('.panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('panel-' + btn.dataset.tab).classList.add('active');
  });
});

// ---------- 健康检查 ----------
async function checkHealth(){
  try{
    const r = await fetch('/api/health');
    const j = await r.json();
    const el = $('#health');
    el.classList.add('ok');
    el.innerHTML = `<span class="dot"></span><span>${j.embedding_model.split('/').pop()} · ${j.llm_model}</span>`;
  }catch(e){
    const el = $('#health');
    el.classList.add('err');
    el.innerHTML = `<span class="dot"></span><span>服务未启动</span>`;
  }
}

// ---------- 工具 ----------
function esc(s){return (s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}

// 自动撑高 textarea
function autoGrow(el){
  el.style.height='auto';
  el.style.height = Math.min(el.scrollHeight, 180) + 'px';
}

// 打字机效果
function typeWriter(el, text, speed=14){
  return new Promise(resolve => {
    el.classList.add('caret');
    el.textContent = '';
    let i = 0;
    const tick = () => {
      if(i < text.length){
        el.textContent += text[i++];
        state.typingTimer = setTimeout(tick, speed);
      } else {
        el.classList.remove('caret');
        resolve();
      }
    };
    tick();
  });
}

// ---------- 渲染消息 ----------
function avatarSVG(role){
  if(role==='user'){
    return `<div class="av">你</div>`;
  }
  return `<div class="av">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:16px;height:16px">
      <path d="M12 2L2 7l10 5 10-5-10-5z"/>
      <path d="M2 17l10 5 10-5M2 12l10 5 10-5"/>
    </svg>
  </div>`;
}

function renderMsg(role, content, meta={}){
  const div = document.createElement('div');
  div.className = 'msg ' + role;
  let html = `
    ${avatarSVG(role)}
    <div style="flex:1;min-width:0">
      <div class="bubble">${esc(content)}</div>
  `;
  if(role === 'bot'){
    if(meta.used_kb){
      html += `<div class="meta">
        <span class="tag">📚 已调用知识库</span>
        <span class="tag gray">${meta.citations?.length||0} 条引用</span>
        <span class="cite-btn" data-cites='${esc(JSON.stringify(meta.citations||[]))}'>查看引用 →</span>
      </div>`;
    } else if(meta.used_kb === false){
      html += `<div class="meta"><span class="tag gray">💬 通用回答</span></div>`;
    }
    if(meta.reasoning){
      html += `<details style="margin-top:6px"><summary style="font-size:11px;color:var(--text-2);cursor:pointer">思考过程</summary>
        <div style="margin-top:6px;padding:8px 10px;background:rgba(0,0,0,.25);border-radius:8px;font-size:12px;color:var(--text-2);font-family:JetBrains Mono,monospace;white-space:pre-wrap">${esc(meta.reasoning)}</div>
      </details>`;
    }
  }
  html += '</div>';
  div.innerHTML = html;
  return div;
}

// ---------- Loading 占位 ----------
function loadingMsg(){
  const div = document.createElement('div');
  div.className = 'msg bot loading';
  div.innerHTML = `
    ${avatarSVG('bot')}
    <div style="flex:1;min-width:0">
      <div class="bubble"><div class="dots"><span></span><span></span><span></span></div></div>
    </div>`;
  return div;
}

// ---------- 发送聊天 ----------
async function sendChat(text, listEl, saveToHistory=false){
  if(!text.trim()) return;
  listEl.querySelector('.empty')?.remove();

  listEl.appendChild(renderMsg('user', text));
  const loading = loadingMsg();
  listEl.appendChild(loading);
  listEl.scrollTop = listEl.scrollHeight;

  try{
    const r = await fetch('/api/chat',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({question:text, history: saveToHistory? state.history : []})
    });
    const j = await r.json();
    loading.remove();

    // 占位消息用于打字机
    const placeholder = document.createElement('div');
    placeholder.className = 'msg bot';
    placeholder.innerHTML = `
      ${avatarSVG('bot')}
      <div style="flex:1;min-width:0">
        <div class="bubble"></div>
      </div>`;
    listEl.appendChild(placeholder);
    listEl.scrollTop = listEl.scrollHeight;

    const bubble = placeholder.querySelector('.bubble');
    await typeWriter(bubble, j.answer || '(无回答)');

    // 渲染 meta
    const metaWrap = document.createElement('div');
    metaWrap.className = 'meta';
    let metaHTML = '';
    if(j.used_kb){
      metaHTML += `<span class="tag">📚 已调用知识库</span>
                   <span class="tag gray">${j.citations?.length||0} 条引用</span>
                   <span class="cite-btn" data-cites='${esc(JSON.stringify(j.citations||[]))}'>查看引用 →</span>`;
    } else {
      metaHTML += `<span class="tag gray">💬 通用回答</span>`;
    }
    metaWrap.innerHTML = metaHTML;
    placeholder.querySelector('div[style*="flex:1"]').appendChild(metaWrap);

    if(j.reasoning){
      const det = document.createElement('details');
      det.style.cssText = 'margin-top:8px';
      det.innerHTML = `<summary style="font-size:11px;color:var(--text-2);cursor:pointer">思考过程</summary>
        <div style="margin-top:6px;padding:8px 10px;background:rgba(0,0,0,.25);border-radius:8px;font-size:12px;color:var(--text-2);font-family:JetBrains Mono,monospace;white-space:pre-wrap;line-height:1.6">${esc(j.reasoning)}</div>`;
      placeholder.querySelector('div[style*="flex:1"]').appendChild(det);
    }

    listEl.scrollTop = listEl.scrollHeight;

    if(saveToHistory){
      state.history.push({role:'user', content:text});
      state.history.push({role:'assistant', content:j.answer});
      state.lastCitations = j.citations || [];
    }
  }catch(e){
    loading.remove();
    listEl.appendChild(renderMsg('bot', '❌ 请求失败:'+e.message));
  }
}

// ---------- 引用面板 ----------
document.addEventListener('click', e => {
  if(e.target.classList.contains('cite-btn') || e.target.classList.contains('chip')){
    if(e.target.classList.contains('cite-btn')){
      const cites = JSON.parse(e.target.dataset.cites || '[]');
      showCitations(cites);
      $$('.nav-item').forEach(b => b.classList.remove('active'));
      $$('.panel').forEach(p => p.classList.remove('active'));
      document.querySelector('.nav-item[data-tab="cites"]').classList.add('active');
      document.getElementById('panel-cites').classList.add('active');
    }
    if(e.target.classList.contains('chip')){
      const input = e.target.closest('.panel').querySelector('textarea');
      if(input){
        input.value = e.target.textContent;
        autoGrow(input);
        input.focus();
      }
    }
  }
});

function showCitations(cites){
  const panel = $('#citePanel');
  if(!cites || !cites.length){
    panel.className = 'placeholder';
    panel.textContent = '这次回答没有引用片段';
    return;
  }
  panel.className = '';
  panel.innerHTML = cites.map((c,i)=>`
    <div class="cite-item">
      <div class="cite-head">
        <div class="cite-src">【片段${i+1}】 ${esc(c.doc_name)}</div>
        <div class="cite-score">chunk_id=${esc(c.chunk_id)} · 相关度=${c.score.toFixed(3)}</div>
      </div>
      <div class="cite-text">${esc(c.text)}</div>
    </div>
  `).join('');
}

// ---------- 智能问答 ----------
$('#chatSend').addEventListener('click', () => {
  const t = $('#chatInput').value.trim();
  if(!t) return;
  $('#chatInput').value=''; autoGrow($('#chatInput'));
  sendChat(t, $('#chatList'), false);
});
$('#chatInput').addEventListener('keydown', e => {
  if(e.key==='Enter' && !e.shiftKey){e.preventDefault(); $('#chatSend').click();}
});
$('#chatInput').addEventListener('input', e => autoGrow(e.target));

// ---------- 多轮对话 ----------
$('#convSend').addEventListener('click', () => {
  const t = $('#convInput').value.trim();
  if(!t) return;
  $('#convInput').value=''; autoGrow($('#convInput'));
  sendChat(t, $('#convList'), true);
});
$('#convInput').addEventListener('keydown', e => {
  if(e.key==='Enter' && !e.shiftKey){e.preventDefault(); $('#convSend').click();}
});
$('#convInput').addEventListener('input', e => autoGrow(e.target));
$('#convClear').addEventListener('click', () => {
  state.history = [];
  state.lastCitations = [];
  $('#convList').innerHTML = `<div class="empty">
    <div class="empty-icon">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
      </svg>
    </div>
    <div class="empty-title">已清空,重新开始吧</div>
  </div>`;
});

// ---------- 知识库统计 ----------
async function loadKbStats(){
  try{
    const r = await fetch('/api/kb/stats');
    const j = await r.json();
    $('#statDocs').textContent = j.doc_count;
    $('#statChunks').textContent = j.chunk_count;

    const ul = $('#docList');
    ul.innerHTML = j.docs.length ? j.docs.map(d => `
      <li>
        <div>
          <div class="doc-name">${esc(d.doc_name)}</div>
          <div class="doc-meta">doc_id=${esc(d.doc_id)} · ${d.chunk_count} 块</div>
        </div>
        <button class="del-btn" data-id="${esc(d.doc_id)}" title="移除">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
          </svg>
        </button>
      </li>
    `).join('') : '<li style="background:transparent;border:none;text-align:center;color:var(--text-2);padding:20px">暂无文档</li>';

    ul.querySelectorAll('.del-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        if(!confirm('确定移除该文档及其全部向量?')) return;
        await fetch('/api/kb/doc/'+btn.dataset.id, {method:'DELETE'});
        loadKbStats();
      });
    });
  }catch(e){
    console.error(e);
  }
}

function renderPreview(doc){
  const pre = $('#chunkPreview');
  if(!doc.preview || !doc.preview.length){
    pre.innerHTML = '<div class="placeholder">该文件未产生有效分块</div>';
    return;
  }
  pre.innerHTML = `
    <div style="margin-bottom:14px;color:var(--text-2);font-size:12px;font-family:JetBrains Mono,monospace">
      ${esc(doc.doc_name)} · 共 ${doc.chunk_count} 块 · 预览前 ${doc.preview.length}
    </div>
    ${doc.preview.map(c => `
      <div class="ck">
        <div class="ck-meta">
          <span>${esc(c.chunk_id)}</span>
          <span>${c.metadata?.char_len||0} 字符</span>
        </div>
        <div class="ck-text">${esc(c.text)}</div>
      </div>
    `).join('')}
  `;
}

// ---------- 文件上传 ----------
const fileInput = $('#fileInput');
const fileDrop = $('#fileDrop');
const fileNameEl = $('#fileName');

fileInput.addEventListener('change', e => {
  const f = e.target.files[0];
  if(f) fileNameEl.textContent = f.name;
});

['dragenter','dragover'].forEach(ev =>
  fileDrop.addEventListener(ev, e => {e.preventDefault(); fileDrop.classList.add('drag')}));
['dragleave','drop'].forEach(ev =>
  fileDrop.addEventListener(ev, e => {e.preventDefault(); fileDrop.classList.remove('drag')}));
fileDrop.addEventListener('drop', e => {
  const f = e.dataTransfer.files[0];
  if(f){
    const dt = new DataTransfer();
    dt.items.add(f);
    fileInput.files = dt.files;
    fileNameEl.textContent = f.name;
  }
});

$('#btnPreview').addEventListener('click', async () => {
  const f = fileInput.files[0];
  if(!f){alert('请先选择文件');return;}
  setIngestMsg('解析中...');
  const fd = new FormData(); fd.append('file', f);
  try{
    const r = await fetch('/api/parse/preview', {method:'POST', body:fd});
    if(!r.ok) throw new Error(await r.text());
    const j = await r.json();
    renderPreview(j);
    setIngestMsg('✅ 预览完成(尚未入库)', 'ok');
  }catch(e){
    setIngestMsg('❌ 失败:'+e.message, 'err');
  }
});

$('#btnIngest').addEventListener('click', async () => {
  const f = fileInput.files[0];
  if(!f){alert('请先选择文件');return;}
  setIngestMsg('入库中(嵌入模型可能耗时数十秒)...');
  $('#btnIngest').disabled = true;
  try{
    const fd = new FormData(); fd.append('file', f);
    const r = await fetch('/api/ingest/upload', {method:'POST', body:fd});
    if(!r.ok) throw new Error(await r.text());
    const j = await r.json();
    setIngestMsg(`✅ ${j.message} · 新增 ${j.chunk_count} 块 · 总计 ${j.total_chunks}`, 'ok');
    loadKbStats();
  }catch(e){
    setIngestMsg('❌ 入库失败:'+e.message, 'err');
  }finally{
    $('#btnIngest').disabled = false;
  }
});

function setIngestMsg(text, level=''){
  const el = $('#ingestMsg');
  el.textContent = text;
  el.className = 'msg-line ' + level;
}

// ---------- 启动 ----------
checkHealth();
loadKbStats();