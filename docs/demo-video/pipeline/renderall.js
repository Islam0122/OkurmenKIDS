const { chromium } = require('playwright');
const [,, out, fps = 30, workers = 3] = process.argv;
(async () => {
  const b = await chromium.launch();
  const page0 = await b.newPage({ viewport: { width: 1920, height: 1080 } });
  await page0.goto('file://' + __dirname + '/stage/index.html'); const dur = await page0.evaluate(() => window.DURATION); await page0.close();
  const N = Math.round(dur * fps); console.log('frames', N); const t0 = Date.now();
  await Promise.all([...Array(+workers).keys()].map(async (w) => {
    const p = await b.newPage({ viewport: { width: 1920, height: 1080 } });
    p.on('pageerror', e => console.log('ERR', e.message));
    await p.goto('file://' + __dirname + '/stage/index.html'); await p.evaluate(() => window.ready);
    for (let i = w; i < N; i += +workers) {
      await p.evaluate(t => render(t), i / fps);
      await p.screenshot({ path: `${out}/f${String(i).padStart(5, '0')}.jpg`, type: 'jpeg', quality: 93 });
      if (w === 0 && i % 300 === 0) console.log(i, ((Date.now() - t0) / 1000).toFixed(0) + 's');
    }
  }));
  await b.close(); console.log('done', ((Date.now() - t0) / 1000).toFixed(0));
})();
