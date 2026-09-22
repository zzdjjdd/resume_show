/* ============================================================
   ZZD · Personal Site — Interactions
   ============================================================ */
'use strict';

/* ---------- 0. Kaggle data ---------- */
const KAGGLE = [
  { title:'TensorFlow - Help Protect the Great Barrier Reef', year:'2021', medals:[['银',1]],
    desc:'水下视频中的海星目标检测，用于大堡礁珊瑚生态保护。' },
  { title:'Sartorius - Cell Instance Segmentation', year:'2022', medals:[['银',1]],
    desc:'显微镜图像中的细胞实例分割，服务于神经科学研究中的细胞形态分析。' },
  { title:'Happywhale - Whale and Dolphin Identification', year:'2022', medals:[['银',1]],
    desc:'鲸豚个体识别，基于背鳍等局部特征的细粒度分类任务。' },
];

function renderTimeline(){
  const wrap = document.getElementById('timeline');
  if(!wrap) return;
  wrap.innerHTML = KAGGLE.map(k=>{
    const medals = k.medals.map(([type,n])=>{
      const cls = type==='银' ? 'medal-silver':'medal-bronze';
      return `<span class="medal ${cls}">${n} ${type}牌</span>`;
    }).join('');
    return `<article class="t-item reveal">
      <div class="panel-scan"></div>
      <div class="t-top">
        <span class="t-title">${k.title}</span>
        <span class="t-year">// ${k.year}</span>
      </div>
      <p class="t-desc">${k.desc}</p>
      <div class="medals">${medals}</div>
    </article>`;
  }).join('');
}

/* ---------- 1. Starfield canvas ---------- */
function startStarfield(){
  const canvas = document.getElementById('starfield');
  const ctx = canvas.getContext('2d');
  let w, h, stars = [], nodes = [];
  const mouse = { x:-9999, y:-9999 };
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function resize(){
    w = canvas.width = window.innerWidth;
    h = canvas.height = window.innerHeight;
    const starCount = Math.min(220, Math.floor(w*h/9000));
    stars = Array.from({length:starCount}, ()=>({
      x:Math.random()*w, y:Math.random()*h,
      z:Math.random()*0.8+0.2, r:Math.random()*1.3+0.2,
      tw:Math.random()*Math.PI*2
    }));
    const nodeCount = Math.min(70, Math.floor(w/22));
    nodes = Array.from({length:nodeCount}, ()=>({
      x:Math.random()*w, y:Math.random()*h,
      vx:(Math.random()-.5)*0.28, vy:(Math.random()-.5)*0.28
    }));
  }

  function frame(){
    ctx.clearRect(0,0,w,h);

    // stars
    for(const s of stars){
      s.tw += 0.02;
      const a = 0.4 + Math.sin(s.tw)*0.35;
      s.y += s.z*0.15;
      if(s.y > h) s.y = 0;
      ctx.beginPath();
      ctx.arc(s.x, s.y, s.r, 0, Math.PI*2);
      ctx.fillStyle = `rgba(180,230,245,${a*s.z})`;
      ctx.fill();
    }

    // constellation nodes + links
    for(const n of nodes){
      n.x += n.vx; n.y += n.vy;
      if(n.x<0||n.x>w) n.vx*=-1;
      if(n.y<0||n.y>h) n.vy*=-1;
      const dx = n.x-mouse.x, dy = n.y-mouse.y;
      const md = Math.hypot(dx,dy);
      if(md < 140){ n.x += dx/md*1.2; n.y += dy/md*1.2; }
    }
    for(let i=0;i<nodes.length;i++){
      for(let j=i+1;j<nodes.length;j++){
        const a=nodes[i], b=nodes[j];
        const d = Math.hypot(a.x-b.x, a.y-b.y);
        if(d < 130){
          ctx.beginPath();
          ctx.moveTo(a.x,a.y); ctx.lineTo(b.x,b.y);
          ctx.strokeStyle = `rgba(34,211,238,${(1-d/130)*0.16})`;
          ctx.lineWidth = 1;
          ctx.stroke();
        }
      }
      ctx.beginPath();
      ctx.arc(nodes[i].x, nodes[i].y, 1.4, 0, Math.PI*2);
      ctx.fillStyle = 'rgba(45,212,191,.6)';
      ctx.fill();
    }
    requestAnimationFrame(frame);
  }

  resize();
  window.addEventListener('resize', resize);
  window.addEventListener('mousemove', e=>{ mouse.x=e.clientX; mouse.y=e.clientY; });
  window.addEventListener('mouseout', ()=>{ mouse.x=-9999; mouse.y=-9999; });
  if(!reduce) frame(); else { /* draw one static frame */ frame(); }
}

/* ---------- 2. Boot sequence ---------- */
function bootSequence(){
  const boot = document.getElementById('boot');
  const log = document.getElementById('bootLog');
  const lines = [
    '> initializing neural core ...',
    '> loading LLM weights ......... OK',
    '> mounting competition logs ... OK',
    '> calibrating HUD interface ... OK',
    '> welcome, ZZD.'
  ];
  let i = 0;
  (function next(){
    if(i < lines.length){
      log.textContent += lines[i] + '\n';
      i++;
      setTimeout(next, 260);
    } else {
      setTimeout(()=>{ boot.classList.add('done'); startTyping(); }, 500);
    }
  })();
}

/* ---------- 3. Role typewriter ---------- */
const ROLES = ['LLM 方向工程师','Agent 智能体开发','RAG 检索增强','大模型微调 / 部署','Multi-Agent 架构设计'];
function startTyping(){
  const el = document.getElementById('typeRole');
  if(!el) return;
  let r=0, c=0, deleting=false;
  function tick(){
    const word = ROLES[r];
    if(!deleting){
      c++;
      if(c > word.length){ deleting=true; setTimeout(tick,1300); return; }
    } else {
      c--;
      if(c === 0){ deleting=false; r=(r+1)%ROLES.length; }
    }
    el.innerHTML = word.slice(0,c) + '<span class="cursor">▊</span>';
    setTimeout(tick, deleting?55:110);
  }
  tick();
}

/* ---------- 4. Scroll reveal ---------- */
function initReveal(){
  const io = new IntersectionObserver((entries)=>{
    entries.forEach(e=>{ if(e.isIntersecting){ e.target.classList.add('in'); io.unobserve(e.target); }});
  },{threshold:0.12});
  document.querySelectorAll('.reveal').forEach(el=>io.observe(el));
}

/* ---------- 5. Stat counters ---------- */
function initCounters(){
  const io = new IntersectionObserver((entries)=>{
    entries.forEach(e=>{
      if(!e.isIntersecting) return;
      const el = e.target;
      const target = +el.dataset.count;
      let cur = 0;
      const step = Math.max(1, Math.floor(target/28));
      const t = setInterval(()=>{
        cur += step;
        if(cur >= target){ cur = target; clearInterval(t); }
        el.textContent = cur;
      }, 40);
      io.unobserve(el);
    });
  },{threshold:0.5});
  document.querySelectorAll('.stat-num').forEach(el=>io.observe(el));
}

/* ---------- 6. Nav behavior ---------- */
function initNav(){
  const nav = document.getElementById('nav');
  const toggle = document.getElementById('navToggle');
  const links = document.getElementById('navLinks');
  const anchors = [...links.querySelectorAll('a')];

  window.addEventListener('scroll', ()=>{
    nav.classList.toggle('scrolled', window.scrollY > 40);
  });

  toggle.addEventListener('click', ()=>{
    links.classList.toggle('open');
    toggle.classList.toggle('active');
  });
  anchors.forEach(a=>a.addEventListener('click', ()=>{
    links.classList.remove('open'); toggle.classList.remove('active');
  }));

  // scroll spy
  const sections = anchors.map(a=>document.querySelector(a.getAttribute('href'))).filter(Boolean);
  const spy = new IntersectionObserver((entries)=>{
    entries.forEach(e=>{
      if(e.isIntersecting){
        anchors.forEach(a=>a.classList.toggle('active', a.getAttribute('href')==='#'+e.target.id));
      }
    });
  },{threshold:0.4, rootMargin:'-20% 0px -50% 0px'});
  sections.forEach(s=>spy.observe(s));
}

/* ---------- init ---------- */
document.addEventListener('DOMContentLoaded', ()=>{
  renderTimeline();
  startStarfield();
  initReveal();
  initCounters();
  initNav();
  bootSequence();
});
