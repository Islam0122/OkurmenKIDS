const { record } = require('./lib');

const S = {
  // ~31s
  website: (h) => record('website', async (h) => {
    const p = h.page;
    await h.goto('https://www.okurmenkids.com/en', 2500);
    await h.start();
    await h.move(700, 400, 1); await h.wait(1200);
    await h.move(980, 640, 40); await h.wait(1500);
    await h.scroll(820, 3200); await h.wait(1200);
    await h.scroll(820, 3200); await h.wait(1200);
    await h.scroll(900, 3200); await h.wait(1000);
    // Courses page via nav
    await h.scroll(-99999, 1200);
    const courses = p.locator('header a[href$="/courses"]').first();
    await h.click(courses, 2200);
    await h.scroll(700, 3000); await h.wait(1200);
    const projects = p.locator('header a[href$="/projects"]').first();
    await h.click(projects, 2200);
    await h.scroll(650, 3000); await h.wait(1500);
  }),

  // ~54s
  lms: (h) => record('lms', async (h) => {
    const p = h.page;
    await h.goto('https://lms.okurmenkids.com/login', 2000);
    await h.start();
    await h.move(800, 300, 1); await h.wait(600);
    await h.move(800, 470, 30); await h.wait(2600);
    await h.goto('https://lms.okurmenkids.com/schedule/day', 2200);
    await h.move(420, 520, 30); await h.wait(1200);
    await h.scroll(450, 2600); await h.wait(1200);
    await h.scroll(-450, 1500);
    const week = p.getByText('Неделя', { exact: true }).first();
    await h.click(week, 2500);
    await h.scroll(500, 2800); await h.wait(1500);
    await h.goto('https://lms.okurmenkids.com/projects', 2000);
    await h.move(900, 520, 30); await h.wait(1000);
    await h.scroll(700, 3200); await h.wait(1800);
    await h.goto('https://lms.okurmenkids.com/news', 2000);
    await h.scroll(650, 3200); await h.wait(1800);
    await h.goto('https://lms.okurmenkids.com/install', 2000);
    await h.move(700, 420, 30); await h.wait(3500);
  }),

  // ~34s
  admin: (h) => record('admin', async (h) => {
    const p = h.page;
    await h.goto('https://api.okurmenkids.com/admin/', 2000);
    await h.start();
    await h.move(800, 300, 1); await h.wait(500);
    await h.move(800, 520, 30); await h.wait(4500);
    // Local development instance, empty SQLite database (labelled in the edit)
    await h.goto('http://127.0.0.1:8000/admin/login/?next=/admin/', 800);
    await p.fill('[name=username]', 'demo'); await p.fill('[name=password]', 'demo-local-only');
    await p.click('[type=submit]'); await p.waitForLoadState('networkidle'); h.mark(); await h.wait(2500);
    await h.move(150, 400, 30); await h.wait(800);
    const nav = '.main-sidebar .sidebar, .main-sidebar';
    for (let i = 0; i < 5; i++) { await h.scroll(0, 10); await p.evaluate(() => {}); }
    const scroller = await p.evaluate(() => { const c=[...document.querySelectorAll('aside *, nav *')].find(e => e.scrollHeight > e.clientHeight + 50 && getComputedStyle(e).overflowY !== 'visible'); if (c) { c.setAttribute('data-scr','1'); return true;} return false; });
    const sel = scroller ? '[data-scr="1"]' : null;
    await h.scroll(1400, 5000, sel); await h.wait(800);
    await h.scroll(1400, 5000, sel); await h.wait(800);
    const link = p.locator('a[href*="/admin/academy/group/"]').first();
    if (await link.count()) { await h.click(link, 2500); }
    const link2 = p.locator('a[href*="/admin/testing/"]').first();
    if (await link2.count()) { await h.click(link2, 2500); }
    await h.wait(1500);
  }),

  // ~26s (rest of the scene is the animated endpoint chart)
  api: (h) => record('api', async (h) => {
    await h.goto('https://api.okurmenkids.com/', 1000); await h.zoom(2.2);
    await h.start();
    await h.wait(4500);
    await h.goto('https://api.okurmenkids.com/api/v1/', 800); await h.prettyJson(44); await h.wait(4500);
    await h.goto('https://api.okurmenkids.com/api/schema/?format=json', 1500); await h.prettyJson(20);
    await h.wait(2500); await h.scroll(2600, 7000); await h.wait(800);
    await h.goto('https://api.okurmenkids.com/api/v1/public/site/courses/', 1500); await h.prettyJson(20);
    await h.wait(2000); await h.scroll(1400, 5000); await h.wait(1000);
  }),

  // ~31s
  training: (h) => record('training', async (h) => {
    const p = h.page;
    await h.goto('https://training.okurmenkids.com/', 2000);
    await h.start();
    await h.move(700, 400, 1); await h.wait(800);
    await h.move(560, 520, 30); await h.wait(1500);
    await h.scroll(760, 3000); await h.wait(1300);
    await h.scroll(700, 3000); await h.wait(800);
    await h.goto('https://training.okurmenkids.com/training/a9edb7bf-5a7c-4f5a-8153-d57e0cdfa91b', 2000);
    await h.move(700, 380, 30);
    await h.scroll(400, 2000); await h.wait(2500);
    await h.goto('https://training.okurmenkids.com/videos', 1500);
    await h.scroll(500, 2500); await h.wait(1500);
    await h.goto('https://training.okurmenkids.com/materials', 1500);
    await h.scroll(400, 2200); await h.wait(2000);
  }),
};

(async () => { for (const n of process.argv.slice(2)) await S[n](); })();
