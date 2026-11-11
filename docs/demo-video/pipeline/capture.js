const { chromium, devices } = require('playwright');
const OUT = process.argv[2]; const only = process.argv[3];
const BASE = 'http://localhost:5173';
const NOW = new Date(process.env.NOW || '2026-11-12T10:20:00+06:00');
const OFFICE = { latitude: 42.87468, longitude: 74.61228, accuracy: 12 };
async function session(b, user, opts = {}) {
  const ctx = await b.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 2, locale: 'ru-RU',
    timezoneId: 'Asia/Bishkek', geolocation: OFFICE, permissions: ['geolocation'], ...opts });
  const p = await ctx.newPage(); await p.clock.setFixedTime(NOW);
  if (user) {
    await p.goto(BASE + '/login'); await p.fill('input[name=username]', user); await p.fill('input[name=password]', process.env.DEMO_PASSWORD);
    await p.click('button[type=submit]'); await p.waitForURL(u => !String(u).includes('login'), { timeout: 30000 }); await p.waitForTimeout(1500);
  }
  return { ctx, p };
}
async function settle(p, ms = 3000) {
  await p.waitForLoadState('networkidle', { timeout: 60000 }).catch(() => {});
  await p.waitForFunction(() => !document.body.innerText.match(/Собираем данные|Загрузка…|Загружаем/), null, { timeout: 60000 }).catch(() => {});
  await p.waitForTimeout(ms);
}
async function shot(p, name, path, { wait = 2500, before, full } = {}) {
  if (only && !name.startsWith(only)) return;
  if (path) await p.goto(BASE + path);
  await settle(p, wait);
  if (before) { await before(p); await settle(p, 1500); }
  await p.mouse.move(5, 1075);
  await p.screenshot({ path: `${OUT}/${name}.png`, fullPage: !!full }); console.log('shot', name);
}
(async () => {
  const b = await chromium.launch();
  // guest
  let { ctx, p } = await session(b, null);
  await shot(p, 'login', '/login'); await ctx.close();
  // admin
  ({ ctx, p } = await session(b, 'video_admin'));
  await shot(p, 'analytics', '/app/analytics');
  await shot(p, 'kpi', '/app/kpi');
  await shot(p, 'today', '/app/dashboard', { wait: 4000 });
  await shot(p, 'groups', '/app/groups');
  await shot(p, 'group_detail', '/app/groups/2');
  await shot(p, 'students', '/app/students');
  await shot(p, 'schedule', '/app/schedule', { wait: 4000 });
  await shot(p, 'lesson_today', '/app/lessons/2257');
  await shot(p, 'lesson_done', '/app/lessons/108');
  await shot(p, 'homework', '/app/homework');
  await shot(p, 'hw_detail', '/app/homework/140');
  await shot(p, 'staff_report', '/attendance/management');
  await shot(p, 'locations', '/admin/attendance/locations');
  await shot(p, 'reports', '/app/reports');
  await ctx.close();
  // operations director: dashboards
  ({ ctx, p } = await session(b, 'video_ops'));
  await shot(p, 'ops_dashboard', '/operations');
  await shot(p, 'ops_hr', '/operations/hr');
  await shot(p, 'ops_staff', '/operations/staff-attendance');
  await shot(p, 'ops_tasks', '/operations/tasks');
  await ctx.close();
  // operations director on a phone: real QR check-in
  if (!only || only.startsWith('m_')) {
    ({ ctx, p } = await session(b, 'video_ops', { ...devices['iPhone 13'], locale: 'ru-RU', timezoneId: 'Asia/Bishkek', geolocation: OFFICE, permissions: ['geolocation'] }));
    await p.goto(BASE + '/attendance'); await settle(p, 2000); await p.screenshot({ path: `${OUT}/m_before.png` });
    await p.goto(BASE + '/attendance/scan?office=okurmen-main-office');
    for (let i = 0; i < 12; i++) { await p.waitForTimeout(250); await p.screenshot({ path: `${OUT}/m_flow_${String(i).padStart(2, '0')}.png` }); }
    await settle(p, 2500); await p.screenshot({ path: `${OUT}/m_success.png` });
    await p.goto(BASE + '/attendance'); await settle(p, 2000); await p.screenshot({ path: `${OUT}/m_after.png` });
    console.log('mobile done'); await ctx.close();
  }
  // accountant
  ({ ctx, p } = await session(b, 'demo_accountant'));
  await shot(p, 'acc_home', '/accounting');
  await shot(p, 'payroll', '/accounting/payroll', { before: async (p) => {
    const sel = p.locator('select').first(); const opts = await sel.locator('option').allTextContents(); console.log('opts', opts.slice(0, 14).join('|'));
    const oct = opts.find(o => /Сентябр/i.test(o)); if (oct) await sel.selectOption({ label: oct }); const sels = p.locator('select'); const n = await sels.count(); for (let i=0;i<n;i++){ const t = await sels.nth(i).locator('option').allTextContents(); if (t.some(x=>/^16 –/.test(x))) { console.log('half', t.join('|')); await sels.nth(i).selectOption({ label: t.find(x=>/^16 –/.test(x)) }); } } } });
  await shot(p, 'finance', '/finance');
  await shot(p, 'payments', '/finance/payments');
  await shot(p, 'fin_analytics', '/finance/analytics');
  await shot(p, 'overdue', '/finance/overdue');
  await shot(p, 'fin_student', '/finance/students/2');
  await shot(p, 'acc_analytics', '/accounting/analytics');
  await ctx.close();
  // trainer salary
  ({ ctx, p } = await session(b, 'demo_acc_t1'));
  await shot(p, 'my_salary', '/app/my-salary');
  await ctx.close();
  await b.close();
})();
