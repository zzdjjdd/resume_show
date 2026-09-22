// Context Pilot - Main Application JavaScript

// ============== Global State ==============
let currentMode = 'chat';  // 'chat' or 'demo'
let currentContext = null;
let currentDemoStage = 'stage1_cache';
let currentDemoStep = 0;
let trendData = [];

// ============== DOM Elements ==============
const $ = (id) => document.getElementById(id);
const $$ = (sel) => document.querySelectorAll(sel);

// ============== Initialization ==============
document.addEventListener('DOMContentLoaded', () => {
    setupEventListeners();
    refreshContext();
    loadMCPTools();
    loadSettings();
});

// ============== Event Listeners ==============
function setupEventListeners() {
    // Mode switch
    $$('.mode-btn').forEach(btn => {
        btn.addEventListener('click', () => switchMode(btn.dataset.mode));
    });

    // Settings & Reset buttons
    $('btnSettings').addEventListener('click', openSettings);
    $('btnReset').addEventListener('click', resetContext);
    $('btnSaveSettings').addEventListener('click', saveSettings);

    // Send button
    $('btnSend').addEventListener('click', sendMessage);
    $('chatInput').addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Auto-resize textarea
    $('chatInput').addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 120) + 'px';
    });

    // Demo stage tabs
    $$('.stage-tab').forEach(tab => {
        tab.addEventListener('click', () => switchDemoStage(tab.dataset.stage));
    });

    // Demo controls
    $('btnDemoNext').addEventListener('click', executeDemoNext);
    $('btnDemoReset').addEventListener('click', () => {
        currentDemoStep = 0;
        resetContext();
    });

    // Strategy buttons
    $('btnStrategyDelete').addEventListener('click', () => applyStrategy('delete'));
    $('btnStrategySummary').addEventListener('click', () => applyStrategy('summary'));
    $('btnStrategyTrim').addEventListener('click', () => applyStrategy('trim'));

    // Modal strategy buttons
    $('modalDelete').addEventListener('click', () => {
        applyStrategy('delete');
        closeModal();
    });
    $('modalSummary').addEventListener('click', () => {
        applyStrategy('summary');
        closeModal();
    });
    $('modalTrim').addEventListener('click', () => {
        applyStrategy('trim');
        closeModal();
    });

    // Sidebar section collapse
    $$('.sidebar-section.collapsible .sidebar-header').forEach(header => {
        header.addEventListener('click', () => {
            header.parentElement.classList.toggle('collapsed');
        });
    });

    // Settings tabs
    $$('.settings-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            $$('.settings-tab').forEach(t => t.classList.remove('active'));
            $$('.settings-pane').forEach(p => p.classList.remove('active'));
            tab.classList.add('active');
            $(`pane-${tab.dataset.tab}`) || document.querySelector(`[data-pane="${tab.dataset.tab}"]`).classList.add('active');
        });
    });

    // Test connection buttons
    $$('.btn-test').forEach(btn => {
        btn.addEventListener('click', () => testConnection(btn.dataset.test));
    });
}

// ============== Mode Switching ==============
function switchMode(mode) {
    currentMode = mode;
    $$('.mode-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.mode === mode);
    });
    $('demoPanel').style.display = mode === 'demo' ? 'block' : 'none';
    if (mode === 'demo') {
        loadDemoStageInfo();
    }
}

// ============== Demo Mode ==============
async function loadDemoStageInfo() {
    const result = await fetch('/api/demo/steps').then(r => r.json());
    const stage = result[currentDemoStage];
    $('demoStageInfo').textContent = stage.title;
    const step = stage.steps[currentDemoStep];
    $('demoStepInfo').innerHTML = `
        <div class="step-title">${step.title}</div>
        <div>${step.note}</div>
    `;
}

function switchDemoStage(stage) {
    currentDemoStage = stage;
    currentDemoStep = 0;
    $$('.stage-tab').forEach(t => t.classList.toggle('active', t.dataset.stage === stage));
    loadDemoStageInfo();
    resetContext();
}

async function executeDemoNext() {
    try {
        const result = await fetch('/api/demo/execute', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                stage: currentDemoStage,
                step: currentDemoStep
            })
        }).then(r => r.json());

        if (result.detail) {
            alert('演示错误: ' + result.detail);
            return;
        }

        // Add the user message
        addMessageToChat('user', result.user_message, {
            cache_hit: result.user_cache_hit,
            is_demo: true
        });

        // Add the assistant response
        addMessageToChat('assistant', result.response, {
            cache_hit: result.user_cache_hit,
            is_demo: true
        });

        // Update context display
        updateContextDisplay(result.context);

        // Move to next step
        if (result.has_next) {
            currentDemoStep++;
        } else {
            // Loop back to beginning or show completion
            currentDemoStep = 0;
        }
        loadDemoStageInfo();
    } catch (e) {
        console.error('Demo error:', e);
        alert('演示执行错误: ' + e.message);
    }
}

// ============== Chat ==============
async function sendMessage() {
    const input = $('chatInput');
    const msg = input.value.trim();
    if (!msg) return;
    input.value = '';
    input.style.height = 'auto';

    if (currentMode === 'demo') return;

    // Add user message optimistically
    addMessageToChat('user', msg);
    $('btnSend').disabled = true;

    try {
        const result = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: msg, mode: currentMode })
        }).then(r => r.json());

        if (result.detail) {
            alert('错误: ' + result.detail);
            return;
        }

        // Update user message with cache status
        const userBubbles = document.querySelectorAll('.message.user');
        if (userBubbles.length > 0) {
            const lastUser = userBubbles[userBubbles.length - 1];
            const bubble = lastUser.querySelector('.message-bubble');
            const tag = document.createElement('span');
            tag.className = 'cache-tag ' + (result.user_cache_hit ? 'cache-hit' : 'cache-miss');
            tag.textContent = result.user_cache_hit ? '⚡ CACHE' : '🔄 RECALC';
            bubble.appendChild(tag);
            if (result.user_cache_hit) {
                bubble.classList.add('cache-hit');
            }
        }

        // Add assistant response
        addMessageToChat('assistant', result.response, {
            cache_hit: result.user_cache_hit
        });

        // Update context display
        updateContextDisplay(result.context);

        // Show overflow modal if needed
        if (result.overflow) {
            $('modalUsage').textContent = Math.round(result.context.usage_percent) + '%';
            $('strategyModal').style.display = 'flex';
        }
    } catch (e) {
        console.error('Chat error:', e);
        alert('发送失败: ' + e.message);
    } finally {
        $('btnSend').disabled = false;
        $('chatInput').focus();
    }
}

function addMessageToChat(role, content, opts = {}) {
    const messagesDiv = $('chatMessages');
    // Remove welcome message
    const welcome = messagesDiv.querySelector('.welcome-message');
    if (welcome) welcome.remove();

    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${role}`;

    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.textContent = role === 'user' ? '👤' : '🤖';

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    if (opts.cache_hit && role === 'assistant') {
        bubble.classList.add('cache-hit');
    }
    bubble.textContent = content;

    const meta = document.createElement('div');
    meta.className = 'message-meta';
    meta.innerHTML = `<span>${new Date().toLocaleTimeString()}</span>`;

    msgDiv.appendChild(avatar);
    msgDiv.appendChild(bubble);
    msgDiv.appendChild(meta);

    messagesDiv.appendChild(msgDiv);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

// ============== Context ==============
async function refreshContext() {
    try {
        const ctx = await fetch('/api/context').then(r => r.json());
        updateContextDisplay(ctx);
    } catch (e) {
        console.error('Refresh error:', e);
    }
}

function updateContextDisplay(ctx) {
    currentContext = ctx;
    if (!ctx) return;

    // Token progress
    const usage = ctx.usage_percent;
    const fill = $('progressFill');
    fill.style.width = Math.min(usage, 100) + '%';
    fill.classList.remove('warning', 'danger');
    if (usage >= 95) fill.classList.add('danger');
    else if (usage >= 80) fill.classList.add('warning');

    $('progressText').textContent = Math.round(usage) + '%';
    $('tokenCount').textContent = ctx.total_tokens;
    $('tokenMax').textContent = ctx.max_tokens;
    $('consoleInfo').textContent = `当前窗口: ${Math.round(usage)}% (${ctx.total_tokens}/${ctx.max_tokens} tokens)`;

    // System prompt
    $('sysTokens').textContent = ctx.system_prompt.tokens;
    $('sysText').textContent = ctx.system_prompt.content;

    // History
    $('historyCount').textContent = ctx.history.count;
    $('historyTokens').textContent = ctx.history.tokens;
    const historyContent = $('historyContent');
    if (ctx.history.messages && ctx.history.messages.length > 0) {
        historyContent.innerHTML = ctx.history.messages.map(m => {
            const content = (m.content || '').substring(0, 100) + (m.content && m.content.length > 100 ? '...' : '');
            const cacheClass = m.cache_hit ? 'cache-hit' : '';
            return `<div class="context-msg ${m.role} ${cacheClass}">
                <span class="msg-role">${m.role}:</span>${escapeHtml(content)}
            </div>`;
        }).join('');
    } else {
        historyContent.innerHTML = '<div style="color:var(--text-light);font-size:11px;">暂无消息</div>';
    }

    // RAG
    $('ragCount').textContent = ctx.rag.count;
    $('ragTokens').textContent = ctx.rag.tokens;
    const ragContent = $('ragContent');
    if (ctx.rag.items && ctx.rag.items.length > 0) {
        ragContent.innerHTML = ctx.rag.items.map(r => {
            const docs = (r.docs || []).map(d => `
                <div class="rag-doc">
                    <div class="rag-doc-title">📄 ${escapeHtml(d.title || d.id || '文档')}</div>
                    <div>${escapeHtml((d.content || '').substring(0, 150))}...</div>
                </div>
            `).join('');
            return `<div style="margin-bottom:6px;">
                <div style="font-size:11px;color:var(--text-light);margin-bottom:4px;">查询: "${escapeHtml(r.query)}"</div>
                ${docs}
            </div>`;
        }).join('');
    } else {
        ragContent.innerHTML = '<div style="color:var(--text-light);font-size:11px;">未触发RAG</div>';
    }

    // Tools
    $('toolCount').textContent = ctx.tools.count;
    $('toolTokens').textContent = ctx.tools.tokens;
    const toolContent = $('toolContent');
    if (ctx.tools.items && ctx.tools.items.length > 0) {
        toolContent.innerHTML = ctx.tools.items.map(t => `
            <div class="tool-call">
                <div class="tool-name">🔧 ${escapeHtml(t.tool)}(${escapeHtml(JSON.stringify(t.args))})</div>
                <div>${escapeHtml(String(t.result).substring(0, 150))}...</div>
            </div>
        `).join('');
    } else {
        toolContent.innerHTML = '<div style="color:var(--text-light);font-size:11px;">未触发工具</div>';
    }

    // Cache stats
    $('cacheHits').textContent = ctx.cache_hits;
    $('cacheMisses').textContent = ctx.cache_misses;

    // Update trend chart
    trendData.push(ctx.total_tokens);
    if (trendData.length > 50) trendData.shift();
    drawTrendChart();
}

function drawTrendChart() {
    const canvas = $('trendChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    if (trendData.length < 2) {
        ctx.fillStyle = '#94a3b8';
        ctx.font = '12px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('暂无数据', w / 2, h / 2);
        return;
    }

    const max = Math.max(...trendData, currentContext?.max_tokens || 100);
    const stepX = w / (trendData.length - 1);

    // Draw grid
    ctx.strokeStyle = 'rgba(99, 102, 241, 0.1)';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
        const y = h - (h / 4) * i;
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(w, y);
        ctx.stroke();
    }

    // Draw line
    const gradient = ctx.createLinearGradient(0, 0, w, 0);
    gradient.addColorStop(0, '#6366f1');
    gradient.addColorStop(1, '#ec4899');
    ctx.strokeStyle = gradient;
    ctx.lineWidth = 2;
    ctx.beginPath();
    trendData.forEach((v, i) => {
        const x = i * stepX;
        const y = h - (v / max) * h;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // Fill area
    const fillGrad = ctx.createLinearGradient(0, 0, 0, h);
    fillGrad.addColorStop(0, 'rgba(99, 102, 241, 0.3)');
    fillGrad.addColorStop(1, 'rgba(99, 102, 241, 0)');
    ctx.fillStyle = fillGrad;
    ctx.lineTo(w, h);
    ctx.lineTo(0, h);
    ctx.closePath();
    ctx.fill();

    // Max line
    if (currentContext) {
        ctx.strokeStyle = 'rgba(239, 68, 68, 0.4)';
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(0, h - (currentContext.max_tokens / max) * h);
        ctx.lineTo(w, h - (currentContext.max_tokens / max) * h);
        ctx.stroke();
        ctx.setLineDash([]);
    }
}

// ============== Context item toggle ==============
function toggleContextItem(type) {
    const content = $(`${type}Content`);
    if (content) {
        content.style.display = content.style.display === 'none' ? 'block' : 'none';
    }
}

// ============== Strategy ==============
async function applyStrategy(strategy) {
    try {
        const result = await fetch('/api/strategy', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ strategy })
        }).then(r => r.json());
        updateContextDisplay(result.context);
        showToast(result.result.note);
    } catch (e) {
        console.error('Strategy error:', e);
        alert('策略执行错误: ' + e.message);
    }
}

// ============== Reset ==============
async function resetContext() {
    if (!confirm('确定要重置所有对话和上下文吗？')) return;
    try {
        const result = await fetch('/api/reset', { method: 'POST' }).then(r => r.json());
        $('chatMessages').innerHTML = `
            <div class="welcome-message">
                <h2>👋 欢迎使用 Context Pilot</h2>
                <p>对话已重置，开始新的对话吧！</p>
            </div>
        `;
        updateContextDisplay(result.context);
        trendData = [];
        showToast('上下文已重置');
    } catch (e) {
        console.error('Reset error:', e);
    }
}

// ============== Settings ==============
async function loadSettings() {
    try {
        const settings = await fetch('/api/settings').then(r => r.json());
        $('llmBaseUrl').value = settings.llm.base_url || '';
        $('llmModel').value = settings.llm.model || '';
        $('llmTemperature').value = settings.llm.temperature || 0.7;
        $('embBaseUrl').value = settings.embedding.base_url || '';
        $('embModel').value = settings.embedding.model || '';
        $('mcpUrl').value = settings.mcp.url || '';
        $('contextWindow').value = settings.context_window || 2048;
        $('tokenMax').textContent = settings.context_window || 2048;
        // Show API key status (masked) and clear input field
        updateKeyStatus('llm', settings.llm);
        updateKeyStatus('emb', settings.embedding);
        updateKeyStatus('mcp', settings.mcp);
    } catch (e) {
        console.error('Load settings error:', e);
    }
}

function updateKeyStatus(prefix, cfg) {
    const input = $(`${prefix}ApiKey`);
    const status = $(`${prefix}KeyStatus`);
    if (!input) return;
    input.value = '';
    input.placeholder = cfg.api_key_set
        ? `已设置: ${cfg.api_key_masked}（留空保持不变，输入新值覆盖）`
        : '输入 API Key';
    if (status) {
        status.textContent = cfg.api_key_set ? '✅ 已配置' : '❌ 未配置';
        status.style.color = cfg.api_key_set ? 'var(--success)' : 'var(--danger)';
    }
}

function openSettings() {
    $('settingsModal').style.display = 'flex';
    loadSettings();
}

function closeSettings() {
    $('settingsModal').style.display = 'none';
}

async function saveSettings() {
    const settings = {
        llm: {
            base_url: $('llmBaseUrl').value,
            api_key: $('llmApiKey').value,
            model: $('llmModel').value,
            temperature: parseFloat($('llmTemperature').value)
        },
        embedding: {
            base_url: $('embBaseUrl').value,
            api_key: $('embApiKey').value,
            model: $('embModel').value
        },
        mcp: {
            url: $('mcpUrl').value,
            api_key: $('mcpApiKey').value
        },
        context_window: parseInt($('contextWindow').value)
    };
    try {
        const result = await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ settings })
        }).then(r => r.json());
        if (result.success) {
            showToast('设置已保存');
            $('tokenMax').textContent = settings.context_window;
            refreshContext();
        }
    } catch (e) {
        alert('保存设置失败: ' + e.message);
    }
}

async function testConnection(type) {
    const resultDiv = $(`${type}TestResult`);
    if (resultDiv) {
        resultDiv.className = 'test-result';
        resultDiv.textContent = '测试中...';
        resultDiv.style.display = 'block';
    }
    try {
        const result = await fetch('/api/test-connection', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type })
        }).then(r => r.json());
        if (resultDiv) {
            if (result.success) {
                resultDiv.className = 'test-result success';
                resultDiv.textContent = '✅ ' + result.message;
            } else {
                resultDiv.className = 'test-result error';
                resultDiv.textContent = '❌ ' + result.message;
            }
        }
    } catch (e) {
        if (resultDiv) {
            resultDiv.className = 'test-result error';
            resultDiv.textContent = '❌ 连接错误: ' + e.message;
        }
    }
}

async function loadMCPTools() {
    try {
        const data = await fetch('/api/mcp/tools').then(r => r.json());
        const list = $('mcpToolsList');
        if (list && data.tools) {
            list.innerHTML = data.tools.map(t => `
                <li>
                    <span class="tool-name-list">${t.name}</span>
                    - ${t.description}
                </li>
            `).join('');
        }
    } catch (e) {
        console.error('Load MCP tools error:', e);
    }
}

// ============== Modal ==============
function closeModal() {
    $('strategyModal').style.display = 'none';
}

// ============== Utilities ==============
function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return String(text || '').replace(/[&<>"']/g, m => map[m]);
}

function showToast(msg) {
    const toast = document.createElement('div');
    toast.style.cssText = `
        position: fixed;
        bottom: 80px;
        left: 50%;
        transform: translateX(-50%);
        background: linear-gradient(135deg, #6366f1 0%, #818cf8 100%);
        color: white;
        padding: 12px 24px;
        border-radius: 10px;
        font-size: 14px;
        font-weight: 500;
        box-shadow: 0 8px 24px rgba(99, 102, 241, 0.3);
        z-index: 1000;
        animation: toastIn 0.3s ease;
    `;
    toast.textContent = msg;
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 2000);
}

// Add toast animation
const style = document.createElement('style');
style.textContent = `
    @keyframes toastIn {
        from { opacity: 0; transform: translateX(-50%) translateY(20px); }
        to { opacity: 1; transform: translateX(-50%) translateY(0); }
    }
`;
document.head.appendChild(style);
