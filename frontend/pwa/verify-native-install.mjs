/**
 * Proves the portal «Install app» button drives Chrome's REAL install flow.
 *
 *   npm run build && npx vite preview --port 4173 &
 *   xvfb-run -a -s "-screen 0 1280x800x24" node pwa/verify-native-install.mjs [http://localhost:4173]
 *
 * Needs a headed Chromium (Playwright) — headless Chromium never fires
 * `beforeinstallprompt` — and a normal (persistent) profile: Chrome does not
 * offer installation in Incognito, which is what `browser.newContext()` is.
 * `--bypass-app-banner-engagement-checks` skips Chrome's «user engaged with
 * the site» wait only. If ImageMagick `import` exists, the native dialog is
 * captured to /tmp/okurmen-native-install.png (it is browser UI, not page).
 */
import { execSync } from 'node:child_process'
import { mkdtempSync } from 'node:fs'
import { createRequire } from 'node:module'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const require = createRequire(import.meta.url)
const { chromium } = require('playwright')
const BASE = process.argv[2] ?? 'http://localhost:4173'
let failed = 0
const check = (name, ok, detail = '') => {
  if (!ok) failed += 1
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? ` — ${detail}` : ''}`)
}

const ctx = await chromium.launchPersistentContext(mkdtempSync(join(tmpdir(), 'okurmen-pwa-')), {
  headless: false,
  locale: 'ru-RU',
  viewport: null,
  args: ['--bypass-app-banner-engagement-checks', '--window-size=1280,800', '--window-position=0,0'],
})
try {
  await ctx.route('**/api/v1/**', (route) => route.fulfill({ status: 401, contentType: 'application/json', body: '{}' }))
  // Observe the REAL event without changing it: count dispatches and prompt() calls.
  await ctx.addInitScript(() => {
    window.__bip = { fired: 0, trusted: false, prevented: false, promptCalls: 0 }
    window.addEventListener('beforeinstallprompt', (event) => {
      window.__bip.fired += 1
      window.__bip.trusted = event.isTrusted
      const native = event.prompt.bind(event)
      event.prompt = () => {
        window.__bip.promptCalls += 1
        return native()
      }
      setTimeout(() => (window.__bip.prevented = event.defaultPrevented))
    }, { capture: true })
  })

  const page = ctx.pages()[0] ?? (await ctx.newPage())
  await page.goto(`${BASE}/portal`)
  await page.waitForFunction(() => navigator.serviceWorker?.controller, null, { timeout: 15000 })
  await page.reload()
  await page.waitForFunction(() => window.__bip.fired > 0, null, { timeout: 20000 }).catch(() => {})
  const before = await page.evaluate(() => window.__bip)
  check('Chrome fired a trusted beforeinstallprompt', before.fired > 0 && before.trusted)
  check('app called preventDefault() (no mini-infobar)', before.prevented)

  const install = page.getByRole('button', { name: 'Установить приложение' })
  check('portal header shows «Установить приложение»', await install.isVisible())
  await install.click()
  await page.waitForTimeout(2000)
  const after = await page.evaluate(() => window.__bip)
  check('click invoked the saved event’s native prompt()', after.promptCalls === 1)
  check('no custom install dialog in the page', (await page.locator('[role=dialog]').count()) === 0)
  try {
    execSync(`import -window root -display ${process.env.DISPLAY} /tmp/okurmen-native-install.png`, { stdio: 'ignore' })
    console.log('      native dialog captured: /tmp/okurmen-native-install.png')
  } catch {
    /* no ImageMagick: screenshot skipped */
  }

  // Accepting happens in browser UI; the outcome reaches the page as `appinstalled`.
  await page.keyboard.press('Escape')
  await page.evaluate(() => window.dispatchEvent(new Event('appinstalled')))
  check('after appinstalled the button becomes «Открыть приложение»',
    await page.getByRole('button', { name: 'Открыть приложение' }).isVisible())
} finally {
  await ctx.close()
}
process.exit(failed ? 1 : 0)
