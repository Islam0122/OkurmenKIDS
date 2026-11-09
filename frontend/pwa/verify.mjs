/**
 * End-to-end PWA checks against a production build in real Chromium.
 *
 *   npm run build && npx vite preview --port 4173 &
 *   node pwa/verify.mjs [http://localhost:4173]
 *
 * Needs Playwright with Chromium (not a project dependency). The API is
 * mocked per test, so no backend is required. Exits non-zero on failure.
 */
import { createRequire } from 'node:module'
import { readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const { chromium } = require('playwright')

const BASE = process.argv[2] ?? 'http://localhost:4173'
const DIST_SW = join(dirname(fileURLToPath(import.meta.url)), '..', 'dist', 'sw.js')
const results = []

function check(name, ok, detail = '') {
  results.push({ name, ok, detail })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? ` — ${detail}` : ''}`)
}

const USER = {
  id: 7, username: 'trainer', email: 't@okurmen.kg', first_name: 'Айгуль', last_name: 'Тренерова',
  role: 'teacher', is_active: true, is_verified: true,
}
const ACCESS = 'access.SECRET-TOKEN-VALUE'
const REFRESH = 'refresh.SECRET-TOKEN-VALUE'

/** Route mocks still answer while the context is offline — fail like a real network would. */
let networkDown = false

/** Mock the whole API: auth + an empty list for everything else. */
async function mockApi(context) {
  await context.route('**/api/v1/**', async (route) => {
    if (networkDown) return route.abort('internetdisconnected')
    const url = new URL(route.request().url())
    const path = url.pathname.replace('/api/v1', '')
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
    if (path === '/auth/login/') return json({ access: ACCESS, refresh: REFRESH, user: USER })
    if (path === '/auth/me/') {
      return route.request().headers().authorization === `Bearer ${ACCESS}` ? json(USER) : json({ detail: 'no' }, 401)
    }
    if (path === '/push/config/') return json({ enabled: false, public_key: '' })
    if (path === '/trainers/me/') {
      return json({ id: 1, user: USER, image: null, position: 'Тренер', is_active: true, phone: '', experience_years: 2,
        hire_date: null, subjects: [], bio: '' })
    }
    if (path.startsWith('/public/news/')) return json({ count: 1, next: null, previous: null, results: [] })
    if (path.endsWith('/count/') || path.includes('unread')) return json({ count: 0 })
    return json({ count: 0, next: null, previous: null, results: [] })
  })
}

async function swControlled(page) {
  await page.waitForFunction(() => navigator.serviceWorker?.controller != null, null, { timeout: 15000 })
}

async function cacheReport(page) {
  return page.evaluate(async () => {
    const out = {}
    for (const name of await caches.keys()) {
      const cache = await caches.open(name)
      const entries = []
      for (const request of await cache.keys()) {
        const response = await cache.match(request)
        entries.push({ url: request.url, body: await response.clone().text() })
      }
      out[name] = entries
    }
    return out
  })
}

const browser = await chromium.launch()

try {
  // 1. Manifest + icons -------------------------------------------------
  {
    const context = await browser.newContext()
    const page = await context.newPage()
    const res = await page.goto(`${BASE}/manifest.webmanifest`)
    const manifest = await res.json()
    check('manifest: name/short_name', manifest.name === 'Okurmen Kids' && manifest.short_name === 'Okurmen')
    check('manifest: standalone, scope, start_url', manifest.display === 'standalone' && manifest.scope === '/' && manifest.start_url === '/portal')
    for (const icon of manifest.icons) {
      const dims = await page.evaluate(async (src) => {
        const img = new Image()
        img.src = src
        await img.decode()
        return `${img.naturalWidth}x${img.naturalHeight}`
      }, new URL(icon.src, BASE).href)
      check(`icon ${icon.src} (${icon.purpose})`, dims === icon.sizes, dims)
    }
    check('manifest: has maskable icons', manifest.icons.some((i) => i.purpose === 'maskable'))
    for (const href of ['/icons/apple-touch-icon.png', '/offline.html', '/splash/apple-splash-1179x2556.png']) {
      const r = await page.goto(new URL(href, BASE).href)
      check(`asset ${href}`, r.ok())
    }
    await context.close()
  }

  // 2. SW registration, installability, shell precache ---------------------
  const context = await browser.newContext()
  await mockApi(context)
  const page = await context.newPage()
  await page.goto(`${BASE}/login`)
  await swControlled(page)
  check('service worker registered and controls the page', true)

  const cdp = await context.newCDPSession(page)
  const { installabilityErrors } = await cdp.send('Page.getInstallabilityErrors')
  check('Chromium installability: no errors', installabilityErrors.length === 0, JSON.stringify(installabilityErrors))
  const appManifest = await cdp.send('Page.getAppManifest')
  check('Chromium parsed manifest without errors', appManifest.errors.length === 0, JSON.stringify(appManifest.errors))

  let caches = await cacheReport(page)
  const shellName = Object.keys(caches).find((n) => n.startsWith('okurmen-shell-'))
  check('app shell precached', Boolean(shellName) && caches[shellName].some((e) => e.url.endsWith('/index.html')))

  // 3. Login, authenticated API untouched by the SW, no secrets in caches ---
  await page.fill('input[name="username"], #username', 'trainer')
  await page.fill('input[type="password"]', 'password123')
  await page.click('button[type="submit"]')
  await page.waitForURL(/\/app\//, { timeout: 15000 })
  check('login works through the service worker', true, new URL(page.url()).pathname)
  await page.goto(`${BASE}/news`)
  await page.waitForLoadState('networkidle')
  caches = await cacheReport(page)
  const allEntries = Object.values(caches).flat()
  const leaks = allEntries.filter((e) => e.body.includes('SECRET-TOKEN') || e.body.includes(USER.email))
  check('no token or personal data in Cache Storage', leaks.length === 0, leaks.map((l) => l.url).join(', '))
  const privateApi = allEntries.filter((e) => e.url.includes('/api/') && !e.url.includes('/api/v1/public/'))
  check('only public API responses are cached', privateApi.length === 0, privateApi.map((e) => e.url).join(', '))
  check('public API response cached for offline', allEntries.some((e) => e.url.includes('/api/v1/public/news/')))

  // 4. Offline navigation ---------------------------------------------------
  await context.setOffline(true)
  networkDown = true
  await page.goto(`${BASE}/app/dashboard`)
  await page.getByText('Сервер недоступен').waitFor({ timeout: 15000 })
  check('offline: app shell boots and shows the offline screen', true)
  // With context.route active, Chromium keeps navigator.onLine === true (a
  // Playwright quirk) — i.e. «internet up, server down»: the screen must say so.
  await page.getByText(/ждём ответа сервера|Нет подключения к интернету/).first().waitFor()
  check('offline: connection status chip is shown', true)
  // Deliver the event the browser sends when the link drops.
  await page.evaluate(() => window.dispatchEvent(new Event('offline')))
  await page.getByText('Изменения не сохранятся', { exact: false }).locator('visible=true').first().waitFor()
  check('offline: banner says nothing is synchronised or saved', true)
  const keptToken = await page.evaluate(() => localStorage.getItem('okurmenkids.access_token'))
  check('offline: session kept (token not discarded)', keptToken === ACCESS, String(keptToken))

  // 5. Recovery -------------------------------------------------------------
  await context.setOffline(false)
  networkDown = false
  await page.evaluate(() => window.dispatchEvent(new Event('online')))
  await page.waitForFunction(() => !document.body.innerText.includes('Сервер недоступен'), null, { timeout: 15000 })
  check('online again: recovers automatically without a click', true)

  // 5b. Cold offline start (no route mocks: real offline emulation) ----------
  {
    const cold = await browser.newContext()
    const coldPage = await cold.newPage()
    await coldPage.goto(`${BASE}/login`)
    await swControlled(coldPage)
    await coldPage.evaluate((t) => localStorage.setItem('okurmenkids.access_token', t), ACCESS)
    await cold.setOffline(true)
    await coldPage.goto(`${BASE}/app/dashboard`)
    await coldPage.getByText('Раздел недоступен без интернета').waitFor({ timeout: 15000 })
    check('cold offline: unopened section explains itself (no blank page)', true)
    check('cold offline: navigator reports offline + banner shown',
      (await coldPage.evaluate(() => navigator.onLine)) === false &&
      (await coldPage.getByText('Нет подключения к интернету').count()) > 0)
    await coldPage.evaluate(() => localStorage.clear())
    await coldPage.close()
    const loginPage = await cold.newPage()
    await loginPage.goto(`${BASE}/login`)
    const loginShown = await loginPage.locator('#username').waitFor({ timeout: 15000 }).then(() => true, () => false)
    check('cold offline: login screen still opens from the precached shell', loginShown,
      loginShown ? '' : (await loginPage.evaluate(() => document.body.innerText)).slice(0, 200))
    await cold.close()
  }

  // 6. Logout clears tokens and the worker's API copies ---------------------
  await page.goto(`${BASE}/app/profile`)
  await page.getByText('Приложение и уведомления').waitFor({ timeout: 15000 })
  check('profile: app settings card rendered', true)
  await page.evaluate(() => {
    localStorage.removeItem('okurmenkids.access_token')
    localStorage.removeItem('okurmenkids.refresh_token')
  })
  await page.evaluate(() => navigator.serviceWorker.controller.postMessage({ type: 'CLEAR_USER_DATA' }))
  await page.waitForTimeout(500)
  caches = await cacheReport(page)
  check('logout message clears API cache', !Object.keys(caches).some((n) => n.startsWith('okurmen-public-api')))

  // 6b. Launch flow: PWA → portal → LMS → dashboard; «Выйти» → portal ------
  {
    await page.evaluate((t) => {
      localStorage.setItem('okurmenkids.access_token', t.a)
      localStorage.setItem('okurmenkids.refresh_token', t.r)
    }, { a: ACCESS, r: REFRESH })
    await page.goto(`${BASE}/portal`) // what the installed app opens (start_url)
    await page.locator('a[data-app="lms"]').waitFor({ timeout: 15000 })
    await page.waitForTimeout(500)
    check('launch: signed-in user stays on /portal (no auto-redirect)', new URL(page.url()).pathname === '/portal')
    await page.locator('a[data-app="lms"]').click()
    await page.waitForURL(/\/app\/dashboard/, { timeout: 15000 })
    check('launch: LMS card → role dashboard (signed in)', true, new URL(page.url()).pathname)
    await page.reload()
    await page.waitForTimeout(800)
    check('refresh on a deep LMS route keeps the session and route', new URL(page.url()).pathname === '/app/dashboard')
    const logoutButton = page.getByRole('button', { name: 'Выйти' }).first()
    await logoutButton.click()
    await page.waitForURL(/\/portal$/, { timeout: 15000 })
    check('«Выйти» returns to the public portal', new URL(page.url()).pathname === '/portal')
    await page.locator('a[data-app="lms"]').click()
    await page.waitForURL(/\/login/, { timeout: 15000 })
    check('launch: LMS card → /login when signed out', true)
    await page.fill('#username', 'trainer')
    await page.fill('input[type="password"]', 'password123')
    await page.click('button[type="submit"]')
    await page.waitForURL(/\/app\//, { timeout: 15000 })
    check('after login → role-based dashboard', true, new URL(page.url()).pathname)
    await page.goto(`${BASE}/app/profile`) // direct deep link
    await page.getByText('Приложение и уведомления').waitFor({ timeout: 15000 })
    check('direct link to an internal LMS page works', new URL(page.url()).pathname === '/app/profile')
  }

  // 7. Update flow ------------------------------------------------------------
  const original = readFileSync(DIST_SW, 'utf8')
  try {
    writeFileSync(DIST_SW, original.replace(/"version":"([0-9a-f]+)"/, '"version":"$1-next"'))
    await page.goto(`${BASE}/news`)
    await page.evaluate(() => navigator.serviceWorker.getRegistration().then((r) => r.update()))
    await page.getByText('Доступна новая версия').waitFor({ timeout: 15000 })
    check('update: new version detected, user is asked', true)
    const reloaded = page.waitForEvent('load', { timeout: 15000 }).catch((e) => e)
    await page.getByRole('button', { name: 'Обновить', exact: true }).click()
    const loadResult = await reloaded
    if (loadResult instanceof Error) throw loadResult
    const names = await page.evaluate(() => caches.keys())
    check('update: reloaded onto the new version, old shell cache removed',
      names.some((n) => n.endsWith('-next')) && names.filter((n) => n.startsWith('okurmen-shell-')).length === 1, names.join(', '))
  } finally {
    writeFileSync(DIST_SW, original)
  }

  await context.close()
} finally {
  await browser.close()
}

const failed = results.filter((r) => !r.ok)
console.log(`\n${results.length - failed.length}/${results.length} checks passed`)
process.exit(failed.length ? 1 : 0)
