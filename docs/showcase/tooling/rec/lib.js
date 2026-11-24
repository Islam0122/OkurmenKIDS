// Browser recorder: CDP screencast frames (JPEG q92) -> constant 30 fps clip via ffmpeg.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const W = 1600, H = 860;

const CURSOR = `
(() => {
  if (window.__fakeCursor) return; window.__fakeCursor = true;
  const add = () => {
    const c = document.createElement('div');
    c.id='__cur';
    c.innerHTML = '<svg width="26" height="26" viewBox="0 0 24 24"><path d="M4 2l16 9-7 2-3 7z" fill="#111" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    Object.assign(c.style,{position:'fixed',left:'0',top:'0',zIndex:2147483647,pointerEvents:'none',transform:'translate(-200px,-200px)',filter:'drop-shadow(0 2px 3px rgba(0,0,0,.35))'});
    document.documentElement.appendChild(c);
    const ring = document.createElement('div');
    Object.assign(ring.style,{position:'fixed',width:'34px',height:'34px',borderRadius:'50%',border:'3px solid rgba(124,58,237,.8)',zIndex:2147483646,pointerEvents:'none',opacity:0,transition:'opacity .5s, transform .5s'});
    document.documentElement.appendChild(ring);
    const last = sessionStorage.getItem('__cur');
    if (last) { const [x,y]=last.split(','); c.style.transform='translate('+x+'px,'+y+'px)'; }
    addEventListener('mousemove', e => { c.style.transform='translate('+(e.clientX-3)+'px,'+(e.clientY-2)+'px)'; try{sessionStorage.setItem('__cur',(e.clientX-3)+','+(e.clientY-2))}catch(_){} }, true);
    addEventListener('mousedown', e => { ring.style.transition='none'; ring.style.left=(e.clientX-17)+'px'; ring.style.top=(e.clientY-17)+'px'; ring.style.opacity=1; ring.style.transform='scale(.5)'; requestAnimationFrame(()=>{ring.style.transition='opacity .6s, transform .6s'; ring.style.opacity=0; ring.style.transform='scale(1.6)';}); }, true);
  };
  if (document.documentElement) add(); else addEventListener('DOMContentLoaded', add);
  // Privacy: blur student names shown as "Firstname X." on public galleries.
  const blur = () => document.querySelectorAll('span,div,p,a,h3,h4').forEach(e => {
    if (e.children.length === 0 && !e.__b && /^[А-ЯЁA-Z][а-яёa-z]+ [А-ЯЁA-Z]\.$/.test((e.textContent||'').trim())) { e.__b = 1; e.style.filter = 'blur(5px)'; }
  });
  setInterval(blur, 100);
})();`;

async function record(name, fn, opts = {}) {
  const outDir = path.join(__dirname, 'out'); fs.mkdirSync(outDir, { recursive: true });
  const fdir = path.join(outDir, name + '_frames'); fs.rmSync(fdir, { recursive: true, force: true }); fs.mkdirSync(fdir);
  const browser = await chromium.launch({ args: ['--hide-scrollbars', '--force-color-profile=srgb'] });
  const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 1, locale: opts.locale || 'en-US', ignoreHTTPSErrors: false });
  await ctx.addInitScript(CURSOR);
  const page = await ctx.newPage();
  const cdp = await ctx.newCDPSession(page);
  const frames = [];
  let idx = 0, recording = false;
  cdp.on('Page.screencastFrame', async (f) => {
    try { await cdp.send('Page.screencastFrameAck', { sessionId: f.sessionId }); } catch (e) {}
    if (!recording) return;
    const fn = path.join(fdir, String(idx++).padStart(6, '0') + '.jpg');
    fs.writeFileSync(fn, Buffer.from(f.data, 'base64'));
    frames.push({ fn, t: f.metadata.timestamp });
  });
  const h = {
    page,
    W, H,
    marks: [],
    mark(t) { if (recording) h.marks.push({ t: (t ?? Date.now() / 1000) - h.t0, url: page.url() }); },
    async start() { await cdp.send('Page.startScreencast', { format: 'jpeg', quality: 92, maxWidth: W, maxHeight: H, everyNthFrame: 1 }); recording = true; h.t0 = Date.now() / 1000; h.mark(); },
    async goto(url, wait = 1500) {
      const ts = Date.now() / 1000;
      await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 }).catch(e => console.log('goto warn', e.message.slice(0, 80)));
      await page.evaluate(() => document.fonts && document.fonts.ready);
      h.mark(ts + 0.25);
      await page.waitForTimeout(wait);
    },
    async prettyJson(fontPx = 19) {
      await page.evaluate((fs) => {
        const pre = document.querySelector('pre'); if (!pre) return;
        let txt = pre.textContent; try { txt = JSON.stringify(JSON.parse(txt), null, 2); } catch (e) {}
        const esc = t => t.replace(/&/g,'&amp;').replace(/</g,'&lt;');
        const html = esc(txt).replace(/("(?:[^"\\]|\\.)*")(\s*:)?|\b(true|false|null)\b|(-?\d+(?:\.\d+)?)/g, (m, str, colon, kw, num) => {
          if (str) return colon ? '<span style="color:#7c3aed">'+str+'</span>'+colon : '<span style="color:#0f766e">'+str+'</span>';
          if (kw) return '<span style="color:#b45309">'+kw+'</span>'; return '<span style="color:#2563eb">'+num+'</span>'; });
        document.body.innerHTML = '<pre style="margin:0;padding:28px 36px;font:'+fs+'px/1.45 \'DejaVu Sans Mono\',monospace;white-space:pre-wrap;word-break:break-word;color:#1f2937">'+html+'</pre>';
        document.body.style.background = '#fbfbfd'; document.body.style.margin = 0;
      }, fontPx);
    },
    async zoom(z) { await page.evaluate((z) => { document.body.style.zoom = z; }, z); },
    async wait(ms) { await page.waitForTimeout(ms); },
    async move(x, y, steps = 25) { await page.mouse.move(x, y, { steps }); },
    async moveTo(locator, steps = 30) {
      const b = await locator.boundingBox(); if (!b) return false;
      await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2, { steps }); return true;
    },
    async click(locator, after = 1500) {
      await h.moveTo(locator); await page.waitForTimeout(250);
      const ts = Date.now() / 1000;
      await page.mouse.down(); await page.mouse.up();
      await page.waitForLoadState('networkidle').catch(() => {});
      await page.waitForTimeout(300); h.mark(ts + 0.2);
      await page.waitForTimeout(after);
    },
    // eased smooth scroll by dy pixels over ms
    async scroll(dy, ms = 2500, sel = null) {
      await page.evaluate(async ([dy, ms, sel]) => {
        const el = sel ? document.querySelector(sel) : null;
        const get = () => el ? el.scrollTop : window.scrollY;
        const set = (v) => el ? (el.scrollTop = v) : window.scrollTo(0, v);
        const s = get(); const t0 = performance.now();
        await new Promise(res => { const step = (now) => { const p = Math.min(1, (now - t0) / ms); const e = p < .5 ? 4*p*p*p : 1 - Math.pow(-2*p + 2, 3) / 2; set(s + dy * e); p < 1 ? requestAnimationFrame(step) : res(); }; requestAnimationFrame(step); });
      }, [dy, ms, sel]);
      await page.waitForTimeout(150);
    },
  };
  h.recording = () => recording;
  await fn(h);
  await page.waitForTimeout(300);
  recording = false;
  await cdp.send('Page.stopScreencast').catch(() => {});
  await browser.close();
  // Build concat list with real frame durations
  const list = [];
  for (let i = 0; i < frames.length; i++) {
    const d = i + 1 < frames.length ? frames[i + 1].t - frames[i].t : 0.3;
    list.push(`file '${frames[i].fn}'\nduration ${Math.max(d, 0.001).toFixed(4)}`);
  }
  list.push(`file '${frames[frames.length - 1].fn}'`);
  const lf = path.join(outDir, name + '.txt'); fs.writeFileSync(lf, list.join('\n'));
  const out = path.join(outDir, name + '.mp4');
  // Screencast timestamps are relative to frames; align marks to first frame time
  const first = frames[0].t; const off = first - h.t0;
  fs.writeFileSync(path.join(outDir, name + '.marks.json'), JSON.stringify(h.marks.map(m => ({ t: Math.max(0, m.t - off), url: m.url })), null, 1));
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', lf, '-vf', `fps=30,scale=${W}:${H}:flags=lanczos,format=yuv420p`, '-c:v', 'libx264', '-crf', '14', '-preset', 'medium', out]);
  const dur = execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', out]).toString().trim();
  console.log(name, 'frames', frames.length, 'dur', dur);
  fs.rmSync(fdir, { recursive: true, force: true });
}
module.exports = { record };
