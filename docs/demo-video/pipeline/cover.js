const { chromium } = require('playwright');
(async () => { const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1920, height: 1080 } });
  await p.goto('file://' + __dirname + '/stage/cover.html'); await p.waitForTimeout(800);
  await p.screenshot({ path: process.argv[2] }); await b.close(); })();
