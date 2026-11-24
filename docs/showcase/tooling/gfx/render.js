// node render.js <scene> <duration> <cuesJSON> <argsJSON> <out.mp4|out.png> [layer-png]
const { chromium } = require('playwright');
const { spawn } = require('child_process');
(async () => {
  const [scene, d, cues, args, out] = process.argv.slice(2);
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1920, height: 1080 } });
  const q = new URLSearchParams({ s: scene, d, cues, a: args });
  await p.goto('file://' + __dirname + '/gfx.html?' + q.toString());
  await p.evaluate(() => document.fonts.ready); await p.waitForTimeout(400);
  if (out.endsWith('.png')) { await p.screenshot({ path: out, omitBackground: true }); await b.close(); return; }
  const fps = 30, n = Math.round(+d * fps);
  const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'mjpeg', '-i', '-', '-c:v', 'libx264', '-crf', '16', '-preset', 'medium', '-pix_fmt', 'yuv420p', '-r', '30', out], { stdio: ['pipe', 'inherit', 'inherit'] });
  for (let i = 0; i < n; i++) {
    await p.evaluate((t) => window.setT(t), i / fps);
    const buf = await p.screenshot({ type: 'jpeg', quality: 93 });
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
  }
  ff.stdin.end(); await new Promise(r => ff.on('close', r)); await b.close();
  console.log('rendered', scene, n, 'frames');
})();
