const { chromium } = require('playwright');
const jobs = JSON.parse(require('fs').readFileSync(process.argv[2]));
(async () => {
  const b = await chromium.launch(); const res = {};
  for (const [user, list] of Object.entries(jobs)) {
    const ctx = await b.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 2, locale: 'ru-RU', timezoneId: 'Asia/Bishkek' });
    const p = await ctx.newPage(); await p.clock.setFixedTime(new Date('2026-11-12T10:20:00+06:00'));
    await p.goto('http://localhost:5173/login'); await p.fill('input[name=username]', user); await p.fill('input[name=password]', process.env.DEMO_PASSWORD);
    await p.click('button[type=submit]'); await p.waitForURL(u => !String(u).includes('login'), { timeout: 30000 });
    for (const [name, path, queries, pre] of list) {
      await p.goto('http://localhost:5173' + path); await p.waitForLoadState('networkidle').catch(()=>{});
      await p.waitForFunction(() => !document.body.innerText.match(/Собираем данные|Загрузка…/), null, { timeout: 60000 }).catch(() => {});
      await p.waitForTimeout(2500);
      if (pre) await p.evaluate(pre).catch(()=>{}), await p.waitForTimeout(2500);
      res[name] = {};
      for (const q of queries) {
        const r = await p.evaluate(([q]) => {
          const [text, up] = q.split('^'); const ups = +(up || 0);
          const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT); let n, el = null;
          while ((n = w.nextNode())) { if (n.textContent.trim() === text || (text.startsWith('~') && n.textContent.includes(text.slice(1)))) { el = n.parentElement; const bb = el.getBoundingClientRect(); if (bb.width > 0) break; el = null; } }
          if (!el) return null;
          for (let i = 0; i < ups; i++) el = el.parentElement;
          const bb = el.getBoundingClientRect(); return [Math.round(bb.x), Math.round(bb.y), Math.round(bb.width), Math.round(bb.height)];
        }, [q]);
        res[name][q] = r;
      }
    }
    await ctx.close();
  }
  console.log(JSON.stringify(res, null, 0)); await b.close();
})();
