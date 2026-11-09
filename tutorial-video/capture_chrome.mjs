/**
 * Real screen recording of the Chrome install flow (no simulated UI).
 *
 *   (cd ../frontend && npm run build)      # the app build that gets recorded
 *   node capture_chrome.mjs                # → build/chrome.mp4 + build/chrome-events.json
 *
 * How it records:
 * - Xvfb display 1920×1080; a headed Chromium (Playwright) with a normal profile
 *   (Chrome installs nothing in Incognito); ffmpeg x11grab records the
 *   actual screen at 30 fps, browser UI included (address bar, Chrome's own
 *   install dialog, the installed app window).
 * - Pointer and keyboard are real X input via xdotool: real typing in the
 *   address bar, real clicks on the page button and on Chrome's dialog.
 * - The sandbox cannot reach Vercel, so requests to the production host are
 *   answered from ../frontend/dist (this repository's build of the same app).
 *   The address bar therefore shows the real address. API calls answer
 *   «signed out».
 * - Every step is logged with its time and screen rectangle
 *   (build/chrome-events.json); render.py places zooms and highlights from it.
 */
import { spawn, execFileSync } from 'node:child_process'
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { createServer } from 'node:https'
import { createRequire } from 'node:module'
import { tmpdir } from 'node:os'
import { dirname, extname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const require = createRequire(join(here, '../frontend/'))
const { chromium } = require('playwright')

const DIST = join(here, '../frontend/dist')
const HOST = 'https://okurmen-kids-drab.vercel.app'
const URL_TEXT = 'okurmen-kids-drab.vercel.app/portal'
const DISPLAY = ':77'
const W = 1920
const H = 1080
const OUT = join(here, 'build')

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const xdo = (...args) => execFileSync('xdotool', args, { env: { ...process.env, DISPLAY } })

const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.png': 'image/png', '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2', '.webmanifest': 'application/manifest+json', '.json': 'application/json', '.ico': 'image/x-icon' }

// --- display + recorder ---------------------------------------------------
const xvfb = spawn('Xvfb', [DISPLAY, '-screen', '0', `${W}x${H}x24`, '-nolisten', 'tcp'], { stdio: 'ignore' })
let rec = null
let server = null
const cleanup = () => {
  rec?.kill('SIGINT')
  server?.close()
  xvfb.kill()
}
process.on('exit', cleanup)
process.on('unhandledRejection', (error) => {
  console.error('FAILED:', error)
  cleanup()
  process.exit(1)
})
await sleep(800)

const events = []
let t0 = 0
const now = () => (Date.now() - t0) / 1000
const log = (event) => {
  events.push({ t: Number(now().toFixed(3)), ...event })
  console.log(`${now().toFixed(2)}s`, event.type, event.label ?? '')
}

/** Smooth, human-like pointer motion (real X pointer). */
let pointer = { x: W / 2, y: H / 2 }
async function moveTo(x, y, ms = 900) {
  const steps = Math.max(12, Math.round(ms / 16))
  const from = { ...pointer }
  for (let i = 1; i <= steps; i += 1) {
    const k = i / steps
    const e = k < 0.5 ? 4 * k * k * k : 1 - (-2 * k + 2) ** 3 / 2 // easeInOutCubic
    xdo('mousemove', String(Math.round(from.x + (x - from.x) * e)), String(Math.round(from.y + (y - from.y) * e)))
    await sleep(ms / steps)
  }
  pointer = { x, y }
}
async function clickRect(rect, label) {
  const cx = Math.round(rect.x + rect.w / 2)
  const cy = Math.round(rect.y + rect.h / 2)
  log({ type: 'focus', label, rect })
  await moveTo(cx, cy)
  await sleep(450)
  log({ type: 'click', label, rect, x: cx, y: cy })
  xdo('click', '1')
}

/** Screen rectangle of a page element (page coordinates + window offset). */
async function screenRect(page, locator) {
  const box = await locator.boundingBox()
  const off = await page.evaluate(() => ({ x: window.screenX + (window.outerWidth - window.innerWidth), y: window.screenY + (window.outerHeight - window.innerHeight) }))
  return { x: Math.round(box.x + off.x), y: Math.round(box.y + off.y), w: Math.round(box.width), h: Math.round(box.height) }
}

/** Grab the screen and find Chrome's install dialog button by its colours. */
function findDialogButton() {
  const shot = join(OUT, 'probe.png')
  execFileSync('import', ['-window', 'root', '-display', DISPLAY, shot])
  const out = execFileSync('/tmp/claude-0/venv/bin/python', [join(here, 'find_dialog.py'), shot]).toString()
  return JSON.parse(out)
}

// --- real HTTPS for the production host --------------------------------------
// Chrome installs PWAs only from a secure origin, and Playwright-fulfilled
// responses do not count. So: a throwaway CA trusted ONLY inside this
// recording profile (its own NSS database), a certificate for the production
// host, a local HTTPS server for ../frontend/dist and a host-resolver rule.
const tls = mkdtempSync(join(tmpdir(), 'okurmen-tls-'))
const home = mkdtempSync(join(tmpdir(), 'okurmen-home-'))
const sh = (cmd, args) => execFileSync(cmd, args, { cwd: tls, stdio: 'ignore' })
sh('openssl', ['req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '2', '-subj', '/CN=Okurmen recording CA',
  '-keyout', 'ca.key', '-out', 'ca.crt', '-addext', 'basicConstraints=critical,CA:TRUE', '-addext', 'keyUsage=critical,keyCertSign'])
sh('openssl', ['req', '-newkey', 'rsa:2048', '-nodes', '-subj', `/CN=${new URL(HOST).host}`, '-keyout', 'site.key', '-out', 'site.csr'])
writeFileSync(join(tls, 'ext.cnf'), `subjectAltName=DNS:${new URL(HOST).host}\nextendedKeyUsage=serverAuth\n`)
sh('openssl', ['x509', '-req', '-in', 'site.csr', '-CA', 'ca.crt', '-CAkey', 'ca.key', '-CAcreateserial', '-days', '2', '-out', 'site.crt', '-extfile', 'ext.cnf'])
mkdirSync(join(home, '.pki/nssdb'), { recursive: true })
execFileSync('certutil', ['-d', `sql:${join(home, '.pki/nssdb')}`, '-N', '--empty-password'])
execFileSync('certutil', ['-d', `sql:${join(home, '.pki/nssdb')}`, '-A', '-t', 'C,,', '-n', 'okurmen-recording-ca', '-i', join(tls, 'ca.crt')])

const PORT = 8443
server = createServer({ key: readFileSync(join(tls, 'site.key')), cert: readFileSync(join(tls, 'site.crt')) }, (req, res) => {
  const url = new URL(req.url, HOST)
  if (url.pathname.startsWith('/api/')) {
    res.writeHead(401, { 'Content-Type': 'application/json' })
    return res.end('{}')
  }
  let file = join(DIST, decodeURIComponent(url.pathname))
  if (url.pathname === '/' || !extname(file) || !existsSync(file)) file = join(DIST, 'index.html')
  res.writeHead(200, { 'Content-Type': TYPES[extname(file)] ?? 'application/octet-stream', 'Cache-Control': 'no-cache' })
  res.end(readFileSync(file))
}).listen(PORT)

// --- browser ----------------------------------------------------------------
const ctx = await chromium.launchPersistentContext(mkdtempSync(join(tmpdir(), 'okurmen-rec-')), {
  headless: false,
  locale: 'ru-RU',
  viewport: null,
  env: { ...process.env, DISPLAY, HOME: home, LANGUAGE: 'ru', LANG: 'ru_RU.UTF-8', LC_ALL: 'ru_RU.UTF-8' }, // Chrome UI in Russian
  ignoreDefaultArgs: ['--enable-automation'], // no «controlled by automated software» bar
  args: [`--window-size=${W},${H}`, '--window-position=0,0', '--bypass-app-banner-engagement-checks', '--lang=ru', '--disable-infobars',
    '--no-first-run', '--disable-features=Prerender2,OmniboxPrerender,Translate,OptimizationHints',
    `--host-resolver-rules=MAP ${new URL(HOST).host}:443 127.0.0.1:${PORT}`, '--no-proxy-server'],
})
// Chrome offers installation only once the page is controlled by its service
// worker; warm that up before recording (a returning visitor's state).
await ctx.addInitScript(() => {
  window.addEventListener('beforeinstallprompt', () => { window.__installOffered = true })
})
const page = ctx.pages()[0] ?? (await ctx.newPage())
await page.goto(`${HOST}/portal`)
await page.waitForFunction(() => navigator.serviceWorker?.controller, null, { timeout: 20000 })
await page.reload()
await page.waitForFunction(() => window.__installOffered === true, null, { timeout: 30000 })
await page.goto('about:blank')
await sleep(1500)

rec = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'x11grab', '-draw_mouse', '1', '-framerate', '30', '-video_size', `${W}x${H}`,
  '-i', `${DISPLAY}.0`, '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '14', '-pix_fmt', 'yuv420p', join(OUT, 'chrome.mp4')], { stdio: ['pipe', 'inherit', 'inherit'] })
t0 = Date.now()
await sleep(1200)

// 1. Open the portal: type the address in the real address bar.
log({ type: 'scene', label: 'open-portal' })
await clickRect({ x: 150, y: 50, w: 700, h: 26 }, 'Адресная строка')
await sleep(250)
xdo('key', 'ctrl+a') // select what is there, so typing replaces it
await sleep(200)
for (const ch of URL_TEXT) {
  xdo('type', '--delay', '0', ch)
  await sleep(55)
}
await sleep(400)
log({ type: 'key', label: 'Enter' })
xdo('key', 'Return')
await page.waitForURL(`${HOST}/portal`)
await page.getByRole('button', { name: 'Установить приложение' }).waitFor()
await page.waitForFunction(() => window.__installOffered === true, null, { timeout: 30000 })
await sleep(1800)
log({ type: 'scene', label: 'portal-loaded' })
await sleep(1500)

// 2. «Установить приложение» in the portal header → Chrome's own dialog.
const install = page.getByRole('button', { name: 'Установить приложение' })
await clickRect(await screenRect(page, install), 'Установить приложение')
await sleep(1600)
const dialog = findDialogButton()
log({ type: 'dialog', label: 'Окно установки Chrome', rect: dialog.dialog })
await sleep(1500)
await clickRect(dialog.install, 'Установить')

// 3. The installed app opens in its own window, at /portal.
const app = await ctx.waitForEvent('page', { timeout: 20000 })
await app.waitForLoadState()
log({ type: 'scene', label: 'app-window' })
await sleep(2500)
const appWin = await app.evaluate(() => ({ x: window.screenX, y: window.screenY, w: window.outerWidth, h: window.outerHeight,
  url: location.pathname, standalone: matchMedia('(display-mode: standalone)').matches }))
log({ type: 'window', label: 'Приложение Okurmen Kids', rect: { x: appWin.x, y: appWin.y, w: appWin.w, h: appWin.h }, url: appWin.url, standalone: appWin.standalone })
await sleep(4000)
log({ type: 'end' })

rec.stdin.write('q')
await new Promise((resolve) => rec.on('close', resolve))
writeFileSync(join(OUT, 'chrome-events.json'), JSON.stringify(events, null, 2))
await ctx.close()
xvfb.kill()
console.log('saved build/chrome.mp4 and build/chrome-events.json')
