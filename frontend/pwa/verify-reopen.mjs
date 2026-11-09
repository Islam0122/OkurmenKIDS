/**
 * Regression test: the INSTALLED app always (re)opens at /portal.
 *
 *   npm run build && npx vite preview --port 4173 &
 *   xvfb-run -a node pwa/verify-reopen.mjs [http://localhost:4173]
 *
 * Installs the app with Chromium's own install code and launches it the way
 * the OS does (Dock, Start menu, home screen): CDP `PWA.install` /
 * `PWA.launch`. Headed Chromium and a normal (persistent) profile are needed,
 * because Chrome installs nothing in Incognito. Three installs:
 *   fresh          installed with start_url /portal
 *   stale          installed with start_url «/» (before the change), new manifest deployed later
 *   never-updated  installed with «/», Chrome never sees a newer manifest:
 *                  every launch really opens «/» (the worst case)
 * For each one, signed in and signed out: launch → open the LMS inside the app →
 * refresh (must stay) → close the window → reopen (must be /portal).
 * The API is mocked. dist/manifest.webmanifest is swapped during the run and restored.
 */
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const { chromium } = require('playwright')

const BASE = process.argv[2] ?? 'http://localhost:4173'
const DIST_MANIFEST = join(dirname(fileURLToPath(import.meta.url)), '..', 'dist', 'manifest.webmanifest')
const current = readFileSync(DIST_MANIFEST, 'utf8')
const legacy = current.replace('"start_url": "/portal"', '"start_url": "/"')
const USER = { id: 7, username: 't', email: 't@okurmen.kg', first_name: 'A', last_name: 'B', role: 'teacher', is_active: true, is_verified: true }

let failed = 0
const check = (name, ok, detail = '') => {
  if (!ok) failed += 1
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? ` — ${detail}` : ''}`)
}
const path = (page) => new URL(page.url()).pathname

async function run(scenario) {
  writeFileSync(DIST_MANIFEST, scenario === 'fresh' ? current : legacy)
  const ctx = await chromium.launchPersistentContext(mkdtempSync(join(tmpdir(), 'okurmen-reopen-')), { headless: false, locale: 'ru-RU' })
  try {
    await ctx.route('**/api/v1/**', (route) => {
      const url = new URL(route.request().url()).pathname
      if (url.endsWith('/auth/me/')) {
        return route.request().headers().authorization ? route.fulfill({ json: USER }) : route.fulfill({ status: 401, json: {} })
      }
      return route.fulfill({ json: { count: 0, next: null, previous: null, results: [] } })
    })
    const tab = ctx.pages()[0] ?? (await ctx.newPage())
    await tab.goto(`${BASE}/news`)
    await tab.waitForFunction(() => navigator.serviceWorker?.controller, null, { timeout: 15000 })
    const cdp = await ctx.newCDPSession(tab)
    const manifestId = `${BASE}/`
    await cdp.send('PWA.install', { manifestId, installUrlOrBundleUrl: `${BASE}/news` })
    await cdp.send('PWA.changeAppUserSettings', { manifestId, displayMode: 'standalone' })
    if (scenario === 'stale') writeFileSync(DIST_MANIFEST, current) // the release ships after the install

    const launch = async () => {
      const opened = ctx.waitForEvent('page', { timeout: 15000 })
      await cdp.send('PWA.launch', { manifestId })
      const app = await opened
      await app.waitForLoadState()
      await app.waitForTimeout(1500)
      const launchedAt = await app.evaluate(() => new URL(performance.getEntriesByType('navigation')[0].name).pathname)
      const standalone = await app.evaluate(() => matchMedia('(display-mode: standalone)').matches)
      return { app, launchedAt, standalone }
    }

    for (const signedIn of [true, false]) {
      await tab.evaluate((on) => {
        if (on) {
          localStorage.setItem('okurmenkids.access_token', 'a')
          localStorage.setItem('okurmenkids.refresh_token', 'r')
        } else {
          localStorage.removeItem('okurmenkids.access_token')
          localStorage.removeItem('okurmenkids.refresh_token')
        }
      }, signedIn)
      const tag = `${scenario}, ${signedIn ? 'signed in' : 'signed out'}`

      let { app, launchedAt, standalone } = await launch()
      check(`[${tag}] launch → /portal in its own window`, path(app) === '/portal' && standalone, `Chrome opened ${launchedAt}`)
      await app.goto(`${BASE}/app/dashboard`)
      await app.waitForTimeout(1200)
      const lms = signedIn ? '/app/dashboard' : '/login'
      check(`[${tag}] LMS inside the app`, path(app) === lms, path(app))
      await app.reload()
      await app.waitForTimeout(1200)
      check(`[${tag}] refresh keeps the route`, path(app) === lms, path(app))
      await app.close() // close the whole app window while on the LMS
      ;({ app, launchedAt } = await launch())
      check(`[${tag}] reopen after closing on the LMS → /portal`, path(app) === '/portal', `Chrome opened ${launchedAt}`)
      await app.close()
    }
  } finally {
    await ctx.close()
  }
}

try {
  for (const scenario of ['fresh', 'stale', 'never-updated']) await run(scenario)
} finally {
  writeFileSync(DIST_MANIFEST, current)
}
process.exit(failed ? 1 : 0)
