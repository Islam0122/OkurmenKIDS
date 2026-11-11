/**
 * Responsive audit of the public website: every route × 11 viewports
 * (360…1920) × languages. Reports horizontal overflow (elements outside the
 * viewport that no container clips), clipped text, broken images, header
 * collisions, error states, console errors, tap targets < 40px, text < 12px.
 *
 * Needs a running site + API with content and Playwright (not a project
 * dependency):  SITE=http://localhost:4173 API=http://127.0.0.1:8000 \
 *               LANGS=ru,ky,en [ONLY=/team,/contacts] node scripts/responsive-audit.cjs
 * Raise the API's PUBLIC_*_RATE limits for the run (hundreds of page loads from one IP).
 */
const { chromium } = require('playwright');
const fs = require('fs');
const BASE = process.env.SITE || 'http://localhost:4173', API = (process.env.API || 'http://127.0.0.1:8000') + '/api/v1/public';
const VIEWPORTS = [[360,800],[375,812],[390,844],[430,932],[768,1024],[820,1180],[1024,768],[1280,800],[1366,768],[1440,900],[1920,1080]];
const langs = (process.env.LANGS || 'ru').split(',');
const only = process.env.ONLY ? process.env.ONLY.split(',') : null;

(async () => {
  const j = async (u) => (await fetch(API + u)).json();
  const slug = {
    course: (await j('/site/courses/')).results[0].slug, project: (await j('/projects/')).results[0].key,
    achievement: (await j('/site/achievements/')).results[0].slug, news: (await j('/news/')).featured.slug,
    event: (await j('/site/events/')).results[0].slug, member: (await j('/site/team/')).results[3].slug,
  };
  const routes = ['/', '/about', '/courses', `/courses/${slug.course}`, '/projects', `/projects/${slug.project}`, '/achievements',
    `/achievements/${slug.achievement}`, '/news', `/news/${slug.news}`, '/events', `/events/${slug.event}`, '/team', `/team/${slug.member}`,
    '/testimonials', '/contacts', '/this-page-does-not-exist'].filter((r) => !only || only.some((o) => r.startsWith(o)));
  const b = await chromium.launch();
  const report = [];
  for (const lang of langs) for (const [w, h] of VIEWPORTS) {
    const ctx = await b.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1, hasTouch: w < 1024 });
    for (const route of routes) {
      const path = (lang === 'ru' ? '' : '/' + lang) + (route === '/' && lang !== 'ru' ? '' : route);
      const p = await ctx.newPage(); const errors = [];
      p.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
      p.on('console', (m) => { if (m.type() === 'error' && !/maps|google|youtube|ytimg|ERR_|404|Failed to load resource/.test(m.text())) errors.push(m.text()); });
      await p.goto(BASE + path, { waitUntil: 'networkidle' }); await p.waitForTimeout(250);
      const r = await p.evaluate(() => {
        const W = document.documentElement.clientWidth, out = { overflow: [], clipped: [], tiny: [], small: [], broken: [], header: null };
        const visible = (el) => { const s = getComputedStyle(el); const r = el.getBoundingClientRect(); return s.visibility !== 'hidden' && s.display !== 'none' && r.width > 0 && r.height > 0 && +s.opacity !== 0; };
        const clippedAncestor = (el) => { for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) { const s = getComputedStyle(a); if (s.overflowX !== 'visible' || s.position === 'fixed') return true } return false };
        const name = (el) => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + '.' + String(el.className && el.className.baseVal === undefined ? el.className : '').split(' ').filter(Boolean).slice(0, 4).join('.') + ' "' + (el.textContent || '').trim().slice(0, 30) + '"';
        for (const el of document.querySelectorAll('body *')) {
          if (!visible(el) || el.closest('[aria-hidden="true"], .sr-only')) continue;
          const r = el.getBoundingClientRect();
          if ((r.right > W + 1 || r.left < -1) && !clippedAncestor(el)) out.overflow.push(name(el) + ` [${Math.round(r.left)}..${Math.round(r.right)}]`);
          const s = getComputedStyle(el);
          const ownText = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
          if (ownText && parseFloat(s.fontSize) < 12 && !el.closest('footer')) out.tiny.push(name(el) + ' ' + s.fontSize);
          if (ownText && el.scrollWidth > el.clientWidth + 1 && s.overflowX !== 'visible' && s.textOverflow !== 'ellipsis' && !/line-clamp|truncate/.test(el.className)) out.clipped.push(name(el));
          if (el.matches('a, button, input, select, textarea, [role=radio], [role=tab]') && !el.closest('p, li > p, blockquote, .prose-site') && s.display !== 'inline') {
            if (r.height < 40 && !(el.matches('a') && el.closest('nav[aria-label="breadcrumb"], footer'))) out.small.push(name(el) + ` ${Math.round(r.width)}x${Math.round(r.height)}`);
          }
        }
        for (const img of document.images) if (img.complete && img.currentSrc && img.naturalWidth === 0 && !/ytimg|youtube|google/.test(img.currentSrc)) out.broken.push(img.currentSrc.slice(-60));
        const header = document.querySelector('header .container-page');
        if (header) { const kids = [...header.children].filter(visible).map((k) => k.getBoundingClientRect()); out.header = { height: Math.round(document.querySelector('header').getBoundingClientRect().height), overlap: kids.some((a, i) => kids.some((c, k) => k > i && a.right > c.left + 1 && c.right > a.left + 1)) } }
        out.errorState = !!document.querySelector('main [role=alert]') && /Маалыматты жүктөө|Не удалось загрузить|Could not load/.test(document.querySelector('main').innerText);
        out.h1 = (() => { const h = document.querySelector('main h1'); return h ? Math.round(parseFloat(getComputedStyle(h).fontSize)) : null })();
        return out;
      });
      report.push({ lang, vp: `${w}x${h}`, route, ...r, errors });
      await p.close();
    }
    await ctx.close();
  }
  await b.close();
  fs.writeFileSync(process.env.REPORT || 'responsive-report.json', JSON.stringify(report, null, 1));
  // summary
  const issues = report.filter((x) => x.errorState || x.overflow.length || x.clipped.length || x.broken.length || x.errors.length || (x.header && x.header.overlap));
  console.log('pages checked:', report.length, 'with blocking issues:', issues.length);
  for (const x of issues) console.log(`${x.lang} ${x.vp} ${x.route} | errorState:${x.errorState} overflow:${x.overflow.length} clipped:${x.clipped.length} broken:${x.broken.length} err:${x.errors.length} hdrOverlap:${x.header?.overlap}\n   ${[...x.overflow.slice(0, 3), ...x.clipped.slice(0, 3), ...x.errors.slice(0, 2)].join('\n   ')}`);
  const small = {}; for (const x of report) for (const s of x.small) { const k = s.replace(/ \d+x\d+$/, ''); small[k] = (small[k] || 0) + 1 }
  console.log('\nsmall tap targets (<40px) by element:'); Object.entries(small).sort((a, c) => c[1] - a[1]).slice(0, 25).forEach(([k, n]) => console.log(n, k));
  const tiny = {}; for (const x of report) for (const s of x.tiny) { const k = s; tiny[k] = (tiny[k] || 0) + 1 }
  console.log('\ntiny text (<12px):'); Object.entries(tiny).sort((a, c) => c[1] - a[1]).slice(0, 15).forEach(([k, n]) => console.log(n, k));
  console.log('\nh1 sizes:', [...new Set(report.map((x) => `${x.vp}:${x.h1}`))].join(' '));
})();
