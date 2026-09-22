/**
 * 渲染进程逻辑：角色交互状态机 + 命中检测（决定鼠标穿透）+ 拖拽 + 闲置动作。
 * 与网页版共享同一套动画，额外通过 window.petAPI 与主进程通信。
 */
'use strict';

const stage  = document.getElementById('stage');
const head   = document.getElementById('head');
const mouth  = document.getElementById('mouth');
const fx     = document.getElementById('fx');
const bubble = document.getElementById('bubble');
const charEl = document.getElementById('char');
const pupils = Array.from(document.querySelectorAll('[data-eye]'));

let idleTimer, actionTimer, blinkTimer;
let locked   = false;        // 播放摸头/害羞等动作时锁定
let muted    = false;        // 静音（音效预留）
let rendering = true;        // 窗口可见时才跑跟随渲染（离屏暂停）
let mouse    = { x: 0.5, y: 0.5 };

// 拖拽状态
let dragging = false;
let moved    = false;        // 区分“点击”与“拖拽”
let downPt   = { x: 0, y: 0 };

/* ---------- 命中检测：鼠标是否落在角色不透明区域 ----------
   透明窗口默认穿透（forward:true 仍收到 mousemove）。
   我们用 document.elementFromPoint 判断指针下是否是角色 SVG 的实心部分，
   命中则请求主进程关闭穿透（可点击/拖拽），否则打开穿透（点桌面）。 */
function hitTest(clientX, clientY) {
  const el = document.elementFromPoint(clientX, clientY);
  if (!el) return false;
  // 命中气泡或角色 SVG 内的图形都算“在角色上”
  return charEl.contains(el) || el === charEl || bubble.contains(el);
}

let lastInteractive = null;
function updateInteractive(on) {
  if (on === lastInteractive) return;   // 去抖，避免每帧 IPC
  lastInteractive = on;
  window.petAPI.setInteractive(on);
}

/* ---------- 气泡 ---------- */
function say(text, ms = 1100) {
  bubble.textContent = text;
  bubble.classList.add('show');
  clearTimeout(say._t);
  say._t = setTimeout(() => bubble.classList.remove('show'), ms);
}

/* ---------- 眼球/头部跟随 ---------- */
function onMove(e) {
  // 命中检测（用视口坐标）
  const over = hitTest(e.clientX, e.clientY);
  updateInteractive(over || dragging);

  const r = stage.getBoundingClientRect();
  mouse.x = (e.clientX - r.left) / r.width;
  mouse.y = (e.clientY - r.top)  / r.height;
  render();

  if (dragging) {
    // 拖拽中：上报屏幕绝对坐标给主进程移动窗口
    if (Math.abs(e.screenX - downPt.x) + Math.abs(e.screenY - downPt.y) > 3) moved = true;
    window.petAPI.dragMove(e.screenX, e.screenY);
  } else {
    // 悬停判定
    if (over && !locked) {
      if (!stage.classList.contains('hover')) enterHover();
    } else if (stage.classList.contains('hover')) {
      leaveHover();
    }
  }
  resetIdle();
}

function render() {
  if (!rendering) return;
  const hx = (mouse.x - 0.5) * 10;
  const hy = (mouse.y - 0.5) * 8;
  head.setAttribute('transform', `translate(${hx.toFixed(2)} ${hy.toFixed(2)})`);
  const px = (mouse.x - 0.5) * 6;
  const py = (mouse.y - 0.5) * 5;
  pupils.forEach(p => p.setAttribute('transform', `translate(${px.toFixed(2)} ${py.toFixed(2)})`));
}

/* ---------- 悬停 ---------- */
function enterHover() {
  if (locked) return;
  stage.classList.remove('idle');
  stage.classList.add('hover');
  setHappy(true);
  say('嘿嘿～');
}
function leaveHover() {
  stage.classList.remove('hover');
  setHappy(false);
  resetIdle();
}

function setHappy(on) {
  // 开心：张嘴笑弧；默认：小微笑（坐标匹配二次元脸型）
  mouth.setAttribute('d', on ? 'M93 110 Q100 119 107 110' : 'M95 111 Q100 115 105 111');
}

/* ---------- 眨眼 ---------- */
function scheduleBlink() {
  clearTimeout(blinkTimer);
  blinkTimer = setTimeout(() => {
    if (rendering) {
      stage.classList.add('blink');
      setTimeout(() => stage.classList.remove('blink'), 120);
    }
    scheduleBlink();
  }, 2600 + Math.random() * 2600);
}

/* ---------- 鼠标按下 / 抬起：拖拽 + 点击区分 ---------- */
document.addEventListener('mousedown', (e) => {
  if (!hitTest(e.clientX, e.clientY)) return;   // 只在角色上响应
  dragging = true;
  moved = false;
  downPt = { x: e.screenX, y: e.screenY };
  updateInteractive(true);
  window.petAPI.dragStart(e.screenX, e.screenY);
});

document.addEventListener('mouseup', (e) => {
  if (dragging) {
    dragging = false;
    window.petAPI.dragEnd();
    if (!moved) handleClick(e);   // 没有明显位移 → 视为点击
    // 抬起后按当前位置重新判定穿透
    updateInteractive(hitTest(e.clientX, e.clientY));
  }
});

/* ---------- 点击：区分头 / 身体 ---------- */
function handleClick(e) {
  if (locked) return;
  const r = stage.getBoundingClientRect();
  const y = (e.clientY - r.top) / r.height;
  if (y < 0.45) patHead();
  else          shyBody();
}

function patHead() {
  lock(900);
  stage.classList.remove('hover');
  stage.classList.add('pat');
  setHappy(true);
  say('好舒服～', 900);
  spawnHearts(6);
  setTimeout(() => { stage.classList.remove('pat'); setHappy(false); }, 520);
}

function shyBody() {
  lock(1100);
  stage.classList.remove('hover');
  stage.classList.add('shy');
  say('呀…别闹啦', 1000);
  setTimeout(() => stage.classList.remove('shy'), 950);
}

/* ---------- 爱心粒子 ---------- */
function spawnHearts(n) {
  for (let i = 0; i < n; i++) {
    const h = document.createElement('div');
    h.className = 'heart';
    h.style.setProperty('--r', (Math.random() * 60 - 30).toFixed(0) + 'deg');
    h.style.left = (38 + Math.random() * 24) + '%';
    h.style.top  = (28 + Math.random() * 10) + '%';
    h.style.animationDelay = (i * 70) + 'ms';
    const hue = 340 + Math.random() * 20;
    h.innerHTML =
      '<svg viewBox="0 0 32 32" width="100%" height="100%">' +
      '<path d="M16 28 C6 20 2 14 2 9 A7 7 0 0 1 16 7 A7 7 0 0 1 30 9 C30 14 26 20 16 28 Z" ' +
      'fill="hsl(' + hue + ' 85% 68%)"/></svg>';
    fx.appendChild(h);
    setTimeout(() => h.remove(), 1300);
  }
}

/* ---------- 动作锁 ---------- */
function lock(ms) { locked = true; clearTimeout(lock._t); lock._t = setTimeout(() => locked = false, ms); }

/* ---------- 闲置：3s 呼吸，之后随机小动作 ---------- */
function resetIdle() {
  clearTimeout(idleTimer);
  clearTimeout(actionTimer);
  stage.classList.remove('idle');
  idleTimer = setTimeout(() => {
    if (!dragging && !locked && !stage.classList.contains('hover')) {
      stage.classList.add('idle');
      scheduleRandomAction();
    }
  }, 3000);
}

function scheduleRandomAction() {
  clearTimeout(actionTimer);
  actionTimer = setTimeout(() => {
    if (stage.classList.contains('idle') && !locked) {
      randomAction();
      scheduleRandomAction();
    }
  }, 8000 + Math.random() * 6000);   // prompt 要求 30s，这里更密集，可自行调大
}

const actions = [
  () => { lock(1600); stage.classList.add('yawn');    say('呼啊～困了', 1400);
          setTimeout(() => stage.classList.remove('yawn'), 1500); },
  () => { lock(1500); stage.classList.add('fixhair'); say('辫子乱了～', 1300);
          setTimeout(() => stage.classList.remove('fixhair'), 1400); },
  () => { lock(2200); stage.classList.add('phone-up'); say('刷会儿手机…', 2000);
          setTimeout(() => stage.classList.remove('phone-up'), 2100); },
];
function randomAction() { actions[Math.floor(Math.random() * actions.length)](); }

/* ---------- 与主进程的事件 ---------- */
window.petAPI.getConfig().then((cfg) => { muted = cfg.muted; });
window.petAPI.onMute((v) => { muted = v; say(v ? '静音了' : '音效开启', 900); });
window.petAPI.onVisibility((visible) => {
  rendering = visible;                 // 隐藏时暂停跟随/眨眼，降低占用
  if (!visible) { stage.classList.remove('idle', 'hover'); }
  else { resetIdle(); }
});

/* ---------- 启动 ---------- */
window.addEventListener('mousemove', onMove);
scheduleBlink();
resetIdle();
render();
