/* 巨构套件 · 源自 ~/Projects/arcology（用户自有项目），2026-10-14 经用户指令移入 Project X 作为桌面端 UI 底座。 */
/* 依赖标记：#boot/#boot-log/#boot-bar、#clock、.reveal、.skill [data-count]、.topbar nav、#progress、.hero-inner。 */
/* MEGASTRUCTURE // 个人终端 — 交互脚本（零依赖） */

const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;

/* ---------- 开机自检 ---------- */
(function boot() {
  const el = $('#boot');
  if (!el) return;
  if (reduce) { el.remove(); return; }

  const log = $('#boot-log');
  const bar = $('#boot-bar i');
  const LINES = [
    'MEGASTRUCTURE OS v2.6 — 个人终端',
    '加载结构载荷 .......... OK',
    '校准重力常数 9.807 ..... OK',
    '接入神经网络 .......... OK',
    '> 欢迎回来，建造者。',
  ];

  function finish() {
    el.classList.add('off');
    setTimeout(() => el.remove(), 450);
    el.removeEventListener('click', skip);
    removeEventListener('keydown', skip);
  }
  function skip() { finish(); }
  el.addEventListener('click', skip);
  addEventListener('keydown', skip);

  let li = 0, ci = 0, out = '';
  (function type() {
    if (li >= LINES.length) { setTimeout(finish, 420); return; }
    const line = LINES[li];
    if (ci < line.length) {
      out += line[ci++];
      log.textContent = out;
      setTimeout(type, 14);
    } else {
      out += '\n'; ci = 0; li++;
      bar.style.width = (li / LINES.length) * 100 + '%';
      setTimeout(type, 110);
    }
  })();
})();

/* ---------- HUD 时钟 ---------- */
(function clock() {
  const el = $('#clock');
  if (!el) return;
  const tick = () => (el.textContent = new Date().toLocaleTimeString('zh-CN', { hour12: false }));
  tick();
  setInterval(tick, 1000);
})();

/* ---------- 进场显现 + 技能计数 ---------- */
function countUp(el, target) {
  if (reduce) { el.textContent = target + '%'; return; }
  const t0 = performance.now(), D = 1100;
  (function frame(now) {
    const p = Math.min(1, (now - t0) / D);
    el.textContent = Math.round(target * (1 - Math.pow(1 - p, 3))) + '%';
    if (p < 1) requestAnimationFrame(frame);
  })(t0);
}

const io = new IntersectionObserver((entries) => {
  entries.forEach((e) => {
    if (!e.isIntersecting) return;
    e.target.classList.add('visible');
    io.unobserve(e.target);
    if (e.target.classList.contains('skill')) {
      const c = e.target.querySelector('[data-count]');
      if (c) countUp(c, +c.dataset.count);
    }
  });
}, { threshold: 0.15 });
$$('.reveal').forEach((el) => io.observe(el));

/* ---------- 导航高亮当前区块 ---------- */
const navLinks = $$('.topbar nav a');
const sectionIO = new IntersectionObserver((entries) => {
  entries.forEach((e) => {
    if (!e.isIntersecting) return;
    navLinks.forEach((a) =>
      a.classList.toggle('active', a.getAttribute('href') === '#' + e.target.id)
    );
  });
}, { rootMargin: '-45% 0px -50% 0px' });
$$('main section[id]').forEach((s) => sectionIO.observe(s));

/* ---------- 滚动：进度条 + Hero 视差 ---------- */
const progress = $('#progress');
const heroInner = $('.hero-inner');
let ticking = false;
addEventListener(
  'scroll',
  () => {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(() => {
      const y = scrollY;
      const max = document.documentElement.scrollHeight - innerHeight;
      progress.style.transform = `scaleX(${max ? y / max : 0})`;
      if (heroInner && !reduce && y < innerHeight) {
        heroInner.style.transform = `translateY(${y * 0.18}px)`;
        heroInner.style.opacity = Math.max(0, 1 - y / (innerHeight * 0.8));
      }
      ticking = false;
    });
  },
  { passive: true }
);
