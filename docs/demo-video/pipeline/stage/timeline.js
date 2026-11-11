// Deterministic timeline: window.render(t) draws the frame at time t (seconds).
const $ = (s) => document.querySelector(s);
const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v));
const ease = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
const easeOut = (x) => 1 - Math.pow(1 - x, 3);
const ramp = (t, a, b, f = ease) => f(clamp((t - a) / (b - a)));
const lerp = (a, b, k) => a + (b - a) * k;
function kf(keys, t) {
  if (t <= keys[0][0]) return keys[0].slice(1);
  for (let i = 0; i < keys.length - 1; i++) {
    const [ta, ...va] = keys[i]; const [tb, ...vb] = keys[i + 1];
    if (t <= tb) { const k = ease((t - ta) / (tb - ta)); return va.map((v, j) => lerp(v, vb[j], k)); }
  }
  return keys[keys.length - 1].slice(1);
}
const inout = (t, a, b, d = 0.5) => Math.min(ramp(t, a, a + d), 1 - ramp(t, b - d, b));

const SC = {
  s1: [0, 16.6], s2: [16.6, 41.2], s3: [41.2, 63.6], s4: [63.6, 88.6], s5: [88.6, 113.8], s6: [113.8, 140.6], s7: [140.6, 166],
};
const LABELS = {
  s2: ['01', 'Dashboard & Analytics', 'Панель руководителя: метрики и KPI в реальном времени'],
  s3: ['02', 'Education Management', 'Группы, расписание, занятия, посещаемость, домашние задания'],
  s4: ['03', 'HR & Attendance', 'QR check-in / check-out, геолокация, отчёты по сотрудникам'],
  s5: ['04', 'Finance & Payroll', 'Оплата обучения и расчёт зарплаты тренеров'],
  s6: ['05', 'Technology & Architecture', 'Как устроена платформа'],
  s7: ['06', 'One Platform', 'Учёба, HR, финансы и администрирование — в одной системе'],
};
const URLS = {
  analytics: '/app/analytics', kpi: '/app/kpi', groups: '/app/groups', students: '/app/students', schedule: '/app/schedule',
  lesson_done: '/app/lessons/108', hw_detail: '/app/homework/140', group_detail: '/app/groups/2', staff_report: '/attendance/management',
  ops_staff: '/operations/staff-attendance', finance: '/finance', payments: '/finance/payments', fin_student: '/finance/students/2',
  overdue: '/finance/overdue', payroll: '/accounting/payroll', my_salary: '/app/my-salary',
};
// [scene, image, localStart, localEnd, camera keys [t, cx, cy, zoom], highlights]
const RAW = [
  ['s2', 'analytics', 0, 11.2, [[0, 960, 540, 1], [2.2, 960, 540, 1], [4.0, 1073, 360, 1.55], [7, 1073, 360, 1.55], [8.8, 1073, 790, 1.4], [11.6, 1073, 820, 1.4]],
    [[4.3, 7.0, 465, 254, 1216, 212], [9.0, 11.2, 465, 558, 1216, 500]]],
  ['s2', 'kpi', 11.2, 18.4, [[0, 960, 540, 1.05], [1.6, 1073, 415, 1.6], [4.8, 1073, 425, 1.6], [7.4, 1073, 700, 1.45]],
    [[1.9, 4.8, 465, 284, 1216, 263]]],
  ['s2', 'analytics', 18.4, 24.6, [[0, 1073, 500, 1.3], [1.8, 1460, 190, 2.1], [6.6, 1460, 195, 2.18]],
    [[2.2, 6.2, 1513, 88, 167, 32]]],
  ['s3', 'groups', 0, 4.6, [[0, 960, 540, 1], [4.8, 1073, 470, 1.25]], []],
  ['s3', 'students', 4.6, 7.4, [[0, 1073, 520, 1.2], [3, 1073, 540, 1.32]], []],
  ['s3', 'schedule', 7.4, 11.4, [[0, 960, 540, 1], [1.5, 1073, 640, 1.45], [4.2, 1073, 660, 1.5]], [[1.8, 4.0, 465, 386, 1216, 690]]],
  ['s3', 'lesson_done', 11.4, 15, [[0, 1073, 470, 1.2], [1.2, 1073, 358, 1.6], [3.8, 1073, 362, 1.62]], [[1.5, 3.6, 465, 232, 1216, 252]]],
  ['s3', 'hw_detail', 15, 19, [[0, 1073, 520, 1.25], [1.6, 1073, 640, 1.35], [3.2, 1480, 960, 1.8], [4.2, 1480, 960, 1.82]], [[3.0, 4.0, 1460, 1016, 220, 48]]],
  ['s3', 'group_detail', 19, 22.4, [[0, 1073, 500, 1.12], [3.6, 1073, 440, 1.3]], []],
  ['s4', 'staff_report', 14.6, 20, [[0, 960, 560, 1], [1.5, 950, 700, 1.38], [5.6, 950, 760, 1.4]], [[2.0, 5.2, 337, 487, 1232, 520]]],
  ['s4', 'ops_staff', 20, 25, [[0, 1073, 520, 1.25], [1.4, 1073, 331, 1.6], [5.2, 1073, 333, 1.62]], [[1.8, 5.0, 465, 272, 1216, 118]]],
  ['s5', 'finance', 0, 5.8, [[0, 960, 540, 1], [2, 1073, 400, 1.35], [6, 1073, 420, 1.38]], []],
  ['s5', 'payments', 5.8, 8.8, [[0, 1073, 500, 1.25], [3.2, 1073, 560, 1.36]], []],
  ['s5', 'fin_student', 8.8, 12.6, [[0, 1073, 450, 1.2], [1.3, 1073, 800, 1.4], [4, 1073, 820, 1.42]], [[1.6, 3.8, 465, 582, 1216, 466]]],
  ['s5', 'overdue', 12.6, 14.6, [[0, 1073, 400, 1.28], [2.2, 1073, 420, 1.4]], []],
  ['s5', 'payroll', 14.6, 20.8, [[0, 960, 540, 1], [1.4, 1073, 250, 1.55], [3, 1073, 250, 1.55], [4.4, 1073, 700, 1.45], [6.4, 1073, 705, 1.47]],
    [[1.6, 3.0, 465, 168, 1216, 154], [4.6, 6.2, 465, 502, 1216, 432]]],
  ['s5', 'my_salary', 20.8, 25.2, [[0, 1073, 500, 1.2], [1.5, 1073, 700, 1.45], [4.6, 1073, 705, 1.47]], [[1.8, 4.4, 465, 512, 1216, 384]]],
];
const CAPS = [
  ['s2', 4.2, 10.8, 'Метрики считаются из реальных учебных данных — без ручных таблиц'],
  ['s2', 12.2, 18.0, 'KPI тренеров формируется автоматически'],
  ['s2', 19.4, 24.0, 'Экспорт отчётов в PDF и Excel'],
  ['s3', 1.0, 6.8, 'Вместо бумажных журналов и чатов'],
  ['s3', 11.8, 21.6, 'Посещаемость и ДЗ → автоматический пересчёт показателей'],
  ['s4', 15.2, 24.4, 'Готовые отчёты по приходу, уходу и опозданиям'],
  ['s5', 0.8, 5.4, 'Кто, сколько и когда должен заплатить'],
  ['s5', 6.2, 12.2, 'Начисления из проведённых уроков · платежи по месяцам договора'],
  ['s5', 15.0, 24.6, 'Зарплата: процент от стоимости курса или оклад + план выплат'],
];

const W = 1560, H = 834, S0 = W / 1920;
const view = $('#view');
const SHOTS = RAW.map(([s, img, a, b, cam, hls]) => {
  const el = document.createElement('div'); el.className = 'shot';
  el.innerHTML = `<img src="img/${img}.png" alt="">`; view.appendChild(el);
  const hlEls = hls.map((h) => { const d = document.createElement('div'); d.className = 'hl'; view.appendChild(d); return [h, d]; });
  const t0 = SC[s][0];
  return { img, a: t0 + a, b: t0 + b, cam: cam.map(([t, ...v]) => [t0 + a + t, ...v]), el, hlEls: hlEls.map(([h, d]) => [[t0 + a + h[0], t0 + a + h[1], ...h.slice(2)], d]) };
});
function camera(sh, t) {
  const [cx, cy, z] = kf(sh.cam, t); const sc = S0 * z;
  const tx = clamp(W / 2 - cx * sc, W - 1920 * sc, 0), ty = clamp(H / 2 - cy * sc, H - 1080 * sc, 0);
  return { sc, tx, ty };
}

// ---------- intro cards ----------
const cards = ['analytics', 'schedule', 'finance'].map((n, i) => {
  const d = document.createElement('div'); d.className = 'card3d'; d.style.width = '540px'; d.style.height = '304px';
  d.innerHTML = `<img src="img/${n}.png" alt="">`; $('#cards3d').appendChild(d); return d;
});
// ---------- architecture ----------
$('#arch').innerHTML = `
<div class="box will" id="bCli" style="left:180px;top:262px;width:480px">
  <h3>Frontend · клиенты</h3><h2>React + TypeScript</h2>
  <p>LMS-кабинеты для 12 ролей, тренинг-портал и публичный сайт академии</p>
  <div class="tags"><span class="tag">React 19</span><span class="tag">TypeScript</span><span class="tag">Vite</span><span class="tag">TanStack Query</span><span class="tag">Tailwind</span><span class="tag dark">PWA · Service Worker</span><span class="tag dark">Web Push</span></div>
  <div class="deploy">Деплой <b>Vercel</b></div></div>
<div class="box will" id="bApi" style="left:760px;top:248px;width:450px">
  <h3>Backend · REST API</h3><h2>Python · Django · DRF</h2>
  <p>Бизнес-логика в сервисном слое, JWT-аутентификация, права по ролям, OpenAPI-схема</p>
  <div class="tags"><span class="tag">Django 6</span><span class="tag">DRF</span><span class="tag">SimpleJWT</span><span class="tag">drf-spectacular</span><span class="tag">ReportLab · openpyxl</span></div>
  <div class="deploy">Деплой <b>Docker</b><b>Railway</b></div></div>
<div class="box will" id="bPg" style="left:1310px;top:220px;width:430px">
  <h3>База данных</h3><h2>PostgreSQL</h2>
  <p>Транзакции и блокировки для денег и отметок, журнал изменений</p></div>
<div class="box will" id="bCel" style="left:1310px;top:470px;width:430px">
  <h3>Фоновые задачи</h3><h2>Redis + Celery</h2>
  <p>• уроки → биллинг каждые 30 мин<br>• просрочки и уведомления бухгалтеру<br>• ежедневные снимки KPI<br>• закрытие незавершённых смен</p></div>
<div class="wire will" id="w1"></div><div class="wire will" id="w2"></div><div class="wire will" id="w3"></div>
<div class="wlabel will" id="l1" style="left:666px;top:420px">HTTPS · JSON</div>
<div class="wlabel will" id="l2" style="left:1222px;top:290px">ORM</div>
<div class="wlabel will" id="l3" style="left:1222px;top:580px">задачи</div>
<div class="dot" id="d1"></div><div class="dot" id="d2"></div><div class="dot" id="d3"></div><div class="dot" id="d4"></div>
<div id="stats" class="abs">
  <div class="stat will"><b data-n="26">26</b><span>Django-приложений</span></div>
  <div class="stat will"><b data-n="154">154</b><span>модели данных</span></div>
  <div class="stat will"><b data-n="3400" data-suf="+">3400+</b><span>автотестов backend</span></div>
  <div class="stat will"><b data-n="12">12</b><span>ролей с правами доступа</span></div>
</div>`;
const WIRES = { w1: [660, 450, 760, 450], w2: [1210, 330, 1310, 315], w3: [1210, 560, 1310, 585] };
for (const [id, [x1, y1, x2, y2]] of Object.entries(WIRES)) {
  const e = $('#' + id); e.style.left = x1 + 'px'; e.style.top = y1 + 'px';
  e.style.width = Math.hypot(x2 - x1, y2 - y1) + 'px'; e.style.transform = `rotate(${Math.atan2(y2 - y1, x2 - x1)}rad)`;
}
// ---------- montage ----------
const TILES = [['today', 'Администратор · «Сегодня»'], ['ops_dashboard', 'Операционный директор'], ['ops_hr', 'HR-менеджер'],
  ['acc_home', 'Бухгалтерия'], ['schedule', 'Расписание академии'], ['m_after', 'Сотрудник · телефон (PWA)']];
const tileEls = TILES.map(([img, lab], i) => {
  const x = 180 + (i % 3) * 530, y = 200 + Math.floor(i / 3) * 360;
  const t = document.createElement('div'); t.className = 'tile will'; t.style.left = x + 'px'; t.style.top = y + 'px';
  t.innerHTML = `<img src="img/${img}.png" alt="">`; if (img === 'm_after') t.querySelector('img').style.objectPosition = 'center 20%';
  const l = document.createElement('div'); l.className = 'tlabel will'; l.style.left = x + 'px'; l.style.top = (y + 296) + 'px'; l.textContent = lab;
  $('#montage').append(t, l); return [t, l];
});

const set = (el, o, tf) => { el.style.opacity = o; if (tf !== undefined) el.style.transform = tf; el.style.visibility = o <= 0.001 ? 'hidden' : 'visible'; };
const sceneAt = (t) => Object.keys(SC).find((k) => t >= SC[k][0] && t < SC[k][1]) || 's7';
const lt = (s, t) => t - SC[s][0];

window.render = function (t) {
  const s = sceneAt(t);
  // ---- label + brand ----
  const lab = LABELS[s];
  const lbl = $('#label');
  if (lab) {
    lbl.querySelector('.num').textContent = lab[0]; lbl.querySelector('.t').textContent = lab[1]; lbl.querySelector('.s').textContent = lab[2];
    const [a, b] = SC[s]; const o = inout(t, a + 0.15, s === 's7' ? a + 12.4 : b + 0.02, 0.6);
    set(lbl, o, `translateY(${(1 - ramp(t, a + 0.15, a + 0.85)) * 18}px)`);
  } else set(lbl, 0);
  const brandO = inout(t, SC.s2[0], SC.s7[0] + 12.4, 0.8);
  set($('#brand'), brandO); set($('#note'), inout(t, SC.s2[0], SC.s6[0], 0.8));

  // ---- frame ----
  const fIn = (a) => ramp(t, a, a + 0.9);
  let fo = 0, fy = 0;
  const segs = [[SC.s2[0] + 0.2, SC.s4[0] + 0.1], [SC.s4[0] + 14.4, SC.s4[1]], [SC.s5[0], SC.s6[0] + 0.2]];
  for (const [a, b] of segs) {
    if (t >= a - 0.01 && t < b + 0.7) {
      const continuing = segs.some(([a2, b2]) => b2 === a && a2 < a);
      const i = (a === SC.s5[0]) ? 1 : fIn(a); const o = 1 - ramp(t, b, b + 0.6);
      fo = Math.min(i, o); fy = (1 - i) * 40 + (1 - o) * -30;
    }
  }
  set($('#frame'), fo, `translateY(${fy}px) scale(${0.97 + 0.03 * fo})`);
  if (fo > 0) {
    let top = null;
    SHOTS.forEach((sh) => {
      const vis = t >= sh.a - 0.01 && t < sh.b + 0.5;
      if (!vis) { sh.el.style.visibility = 'hidden'; sh.hlEls.forEach(([, d]) => (d.style.visibility = 'hidden')); return; }
      const o = (Math.abs(sh.a - SC[sceneOf(sh)][0]) < 0.01 || sh.a === SC.s4[0] + 14.6) ? 1 : ramp(t, sh.a, sh.a + 0.45);
      const { sc, tx, ty } = camera(sh, t);
      set(sh.el, o, `translate(${tx}px, ${ty}px) scale(${sc})`); if (o > 0.5) top = sh;
      sh.hlEls.forEach(([[ha, hb, x, y, w, h], d]) => {
        const ho = inout(t, ha, hb, 0.4) * (t < sh.b ? 1 : 0);
        const px = x * sc + tx - 8, py = y * sc + ty - 8, pw = w * sc + 16, ph = Math.min(h * sc + 16, H - py - 12);
        d.style.left = px + 'px'; d.style.top = py + 'px'; d.style.width = pw + 'px'; d.style.height = ph + 'px'; set(d, ho);
      });
    });
    if (top) $('#url').innerHTML = `okurmen-kids · <b>${URLS[top.img] || ''}</b>`;
  }

  // ---- captions ----
  let cap = null;
  for (const [cs, a, b, text] of CAPS) { const A = SC[cs][0] + a, B = SC[cs][0] + b; if (t >= A && t < B) cap = [A, B, text]; }
  if (cap) { $('#cap').textContent = cap[2]; const o = inout(t, cap[0], cap[1], 0.4); set($('#cap'), o, `translateX(-50%) translateY(${(1 - o) * 14}px)`); }
  else set($('#cap'), 0);

  // ---- intro ----
  const iT = t; const introO = 1 - ramp(t, SC.s1[1] - 0.9, SC.s1[1] + 0.1);
  set($('#intro'), introO > 0 ? 1 : 0);
  if (introO > 0) {
    const up = ramp(iT, 7.0, 8.6); // hero moves up
    const lo = easeOut(clamp(iT / 0.9));
    set($('#logo'), lo * introO, `translateY(${-up * 228}px) scale(${(0.6 + 0.4 * lo) * (1 - 0.42 * up)})`);
    $('#ringArc').style.strokeDashoffset = 628.3 * (1 - ramp(iT, 0.2, 1.5));
    set($('#ring'), clamp(iT / 0.4) * (1 - up) * introO, `scale(${1 + ramp(iT, 1.3, 2.2, easeOut) * 0.06})`);
    const ti = ramp(iT, 1.0, 2.0, easeOut);
    set($('#ititle'), ti * introO, `translateY(${(1 - ti) * 30 - up * 318}px) scale(${1 - 0.36 * up})`);
    const pi = ramp(iT, 2.1, 2.9, easeOut);
    set($('#ipill'), pi * introO, `translateX(-50%) translateY(${(1 - pi) * 20 - up * 330}px) scale(${1 - 0.18 * up})`);
    const si = ramp(iT, 3.4, 4.2, easeOut);
    set($('#isub'), si * (1 - ramp(iT, 6.6, 7.2)) * introO, `translateY(${(1 - si) * 16}px)`);
    cards.forEach((c, i) => {
      const ci = ramp(iT, 7.6 + i * 0.25, 8.8 + i * 0.25, easeOut);
      const x = 180 + i * 580, y = 470 + (1 - ci) * 80 - (iT - 8) * 4 * (i === 1 ? 1.4 : 1);
      c.style.left = x + 'px'; c.style.top = y + 'px';
      set(c, ci * introO, `perspective(1600px) rotateY(${(i - 1) * -10}deg) rotateX(6deg) scale(${0.94 + 0.06 * ci + (iT - 9) * 0.002})`);
    });
    document.querySelectorAll('#chips .chip').forEach((c, i) => {
      const ci = ramp(iT, 9.8 + i * 0.5, 10.5 + i * 0.5, easeOut); set(c, ci * introO, `translateY(${(1 - ci) * 18}px)`);
    });
  }

  // ---- phone scene (s4 0..14.6) ----
  const p0 = SC.s4[0]; const pO = inout(t, p0 + 0.3, p0 + 14.7, 0.7);
  set($('#phoneScene'), pO > 0 ? 1 : 0);
  if (pO > 0) {
    const l = t - p0;
    const pi = ramp(l, 0.3, 1.3, easeOut);
    set($('#phone'), pO, `translateY(${(1 - pi) * 60}px)`);
    set($('#ps1'), ramp(l, 5.2, 5.7), `translateY(${(1 - ramp(l, 5.2, 5.9, easeOut)) * 40}px)`);
    set($('#ps2'), ramp(l, 11.8, 12.3));
    $('#ps0').style.visibility = l < 12.4 ? 'visible' : 'hidden';
    const qi = ramp(l, 0.7, 1.6, easeOut);
    // office card from /admin/attendance/locations: rect 337,295 608x282 -> fit 668x310
    const qs = 668 / 640; const inner = $('#qrcard .inner');
    inner.style.transform = `translate(${-321 * qs}px, ${-279 * qs}px) scale(${qs})`;
    set($('#qrcard'), qi * pO, `translateY(${(1 - qi) * 30}px)`);
    const scan = clamp((l - 2.0) / 3.0);
    $('#beam').style.top = (40 + 230 * (0.5 - 0.5 * Math.cos(scan * Math.PI * 3))) + 'px';
    set($('#beam'), inout(l, 2.0, 5.2, 0.3));
    [2.2, 5.8, 10.4].forEach((a, i) => {
      const e = document.querySelectorAll('#steps .step')[i]; const k = ramp(l, a, a + 0.6, easeOut);
      set(e, k * pO, `translateX(${(1 - k) * 30}px)`);
    });
  }

  // ---- architecture (s6) ----
  const aO = inout(t, SC.s6[0] + 0.4, SC.s6[1] + 0.2, 0.7);
  set($('#arch'), aO > 0 ? 1 : 0);
  if (aO > 0) {
    const l = lt('s6', t);
    const show = (id, a) => { const k = ramp(l, a, a + 0.8, easeOut); set($(id), k * aO, `translateY(${(1 - k) * 30}px)`); return k; };
    show('#bApi', 0.8); show('#bPg', 4.0); show('#bCel', 7.6); show('#bCli', 13.8);
    show('#w2', 4.4); show('#l2', 4.6); show('#w3', 8.0); show('#l3', 8.2); show('#w1', 14.2); show('#l1', 14.4);
    const deps = document.querySelectorAll('.deploy b');
    deps.forEach((d) => { const k = inout(l, 19.6, 23.4, 0.4); d.style.boxShadow = `0 0 0 ${6 * k}px rgba(47,143,91,${0.25 * k})`; });
    const dot = (id, w, a, speed, phase) => {
      const [x1, y1, x2, y2] = WIRES[w]; const e = $('#' + id);
      if (l < a) { set(e, 0); return; }
      let k = ((l - a) * speed + phase) % 2; k = k > 1 ? 2 - k : k;
      e.style.left = lerp(x1, x2, k) + 'px'; e.style.top = lerp(y1, y2, k) + 'px'; set(e, aO);
    };
    dot('d1', 'w1', 15, 0.7, 0); dot('d4', 'w1', 15.5, 0.7, 1); dot('d2', 'w2', 5.2, 0.6, 0); dot('d3', 'w3', 8.8, 0.6, 0.3);
    document.querySelectorAll('#stats .stat').forEach((e, i) => {
      const a = 20.6 + i * 0.35; const k = ramp(l, a, a + 0.7, easeOut); set(e, k * aO, `translateY(${(1 - k) * 24}px)`);
      const b = e.querySelector('b'); const n = +b.dataset.n; const c = ramp(l, a, a + 1.6, easeOut);
      b.textContent = (Math.round(n * c)).toLocaleString('ru-RU') + (b.dataset.suf || '');
    });
  }

  // ---- montage (s7 0..13) + outro ----
  const m0 = SC.s7[0]; const mO = inout(t, m0 + 0.3, m0 + 13.0, 0.8);
  set($('#montage'), mO > 0 ? 1 : 0);
  if (mO > 0) {
    const l = t - m0;
    tileEls.forEach(([tile, labl], i) => {
      const a = 0.6 + i * 0.32; const k = ramp(l, a, a + 0.9, easeOut);
      set(tile, k * mO, `translateY(${(1 - k) * 40}px) scale(${0.96 + 0.04 * k + l * 0.002})`); set(labl, k * mO);
    });
  }
  const oO = ramp(t, m0 + 12.6, m0 + 13.6);
  set($('#outro'), oO > 0 ? 1 : 0);
  if (oO > 0) {
    const l = t - m0;
    const show = (id, a, dy = 24, extra = '') => { const k = ramp(l, a, a + 0.9, easeOut); set($(id), k, `${extra} translateY(${(1 - k) * dy}px)`); };
    const k0 = ramp(l, 12.8, 13.8, easeOut); set($('#olog'), k0, `scale(${0.7 + 0.3 * k0})`);
    show('#otitle', 13.2); const kl = ramp(l, 14.0, 15.0); set($('#oline'), kl, `scaleX(${kl})`);
    show('#otag', 14.4); show('#ostack', 15.6); show('#odev', 16.4);
    // final fade to white
    const fade = ramp(t, SC.s7[1] - 1.2, SC.s7[1]);
    $('#stage').style.filter = fade > 0 ? `opacity(${1 - fade})` : '';
  } else $('#stage').style.filter = '';
};
function sceneOf(sh) { return Object.keys(SC).find((k) => sh.a >= SC[k][0] && sh.a < SC[k][1]); }
window.DURATION = SC.s7[1];
window.ready = Promise.all([...document.images].map((i) => i.decode().catch(() => {}))).then(() => document.fonts.ready);
render(0);
