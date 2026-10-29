/*
 * Запись экранной демонстрации кабинета маркетинга.
 *
 * Открывает локальный фронтенд (Vite, http://127.0.0.1:5173) под демо-учёткой
 * маркетолога и для каждой экранной сцены из build/timing.json выполняет
 * действия точно к началу нужной реплики озвучки. Кадры снимаются через
 * CDP-скринкаст (Page.startScreencast) в 2× разрешении — так приближения в
 * монтаже остаются чёткими. Курсор и «волна» клика рисуются скриптом на
 * странице, поэтому видны в записи.
 *
 * Результат: build/rec/frames/*.jpg и build/rec/events.json (кадры, начала
 * сцен, приближения, подписи).
 *
 * Запуск: node marketing_video/record.cjs   (переменные: APP_URL, DEMO_USER, DEMO_PASSWORD)
 */
const fs = require('fs')
const path = require('path')
let chromium
try { ({ chromium } = require('playwright')) } catch { ({ chromium } = require(path.join(require('child_process').execSync('npm root -g').toString().trim(), 'playwright'))) }

const ROOT = __dirname
const BUILD = path.join(ROOT, 'build')
const REC = path.join(BUILD, 'rec')
const FRAMES = path.join(REC, 'frames')
const APP = process.env.APP_URL || 'http://127.0.0.1:5173'
const USER = process.env.DEMO_USER || 'demo_marketing'
const PASSWORD = process.env.DEMO_PASSWORD || 'demo-video-2026'
const VIEW = { width: 1440, height: 810 }
const DPR = 2

const timing = JSON.parse(fs.readFileSync(path.join(BUILD, 'timing.json'), 'utf8'))
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const now = () => Date.now() / 1000

// Курсор и подсветка клика — внутри страницы, чтобы попасть в скринкаст.
function cursorScript() {
  const install = () => {
    if (document.getElementById('__cur')) return
    const c = document.createElement('div')
    c.id = '__cur'
    c.innerHTML = '<svg width="30" height="30" viewBox="0 0 30 30"><path d="M5 3 L5 24 L10.5 18.8 L14.3 27 L18 25.4 L14.3 17.3 L21.5 17.3 Z" fill="#14181f" stroke="#fff" stroke-width="1.8" stroke-linejoin="round"/></svg>'
    Object.assign(c.style, { position: 'fixed', left: '0', top: '0', width: '30px', height: '30px', pointerEvents: 'none', zIndex: '2147483647', filter: 'drop-shadow(0 2px 3px rgba(0,0,0,.35))', transform: 'translate(-100px,-100px)' })
    document.documentElement.appendChild(c)
    const place = (x, y) => { c.style.transform = `translate(${x - 5}px,${y - 3}px)` }
    try { const p = JSON.parse(sessionStorage.getItem('__curpos') || 'null'); if (p) place(p[0], p[1]) } catch {}
    addEventListener('mousemove', (e) => { place(e.clientX, e.clientY); try { sessionStorage.setItem('__curpos', JSON.stringify([e.clientX, e.clientY])) } catch {} }, true)
    window.__ripple = (x, y) => {
      const r = document.createElement('div')
      Object.assign(r.style, { position: 'fixed', left: `${x - 24}px`, top: `${y - 24}px`, width: '48px', height: '48px', borderRadius: '50%', background: 'rgba(47,143,91,.28)', border: '2px solid rgba(47,143,91,.95)', pointerEvents: 'none', zIndex: '2147483646', transition: 'transform .5s ease-out, opacity .5s ease-out', transform: 'scale(.3)', opacity: '1' })
      document.documentElement.appendChild(r)
      requestAnimationFrame(() => requestAnimationFrame(() => { r.style.transform = 'scale(1.5)'; r.style.opacity = '0' }))
      setTimeout(() => r.remove(), 700)
    }
    addEventListener('mousedown', (e) => window.__ripple(e.clientX, e.clientY), true)
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install)
  else install()
}

function localISO(offsetDays = 0) {
  // «Сегодня» — как на сервере (TIME_ZONE = Asia/Bishkek).
  const d = new Date(`${TODAY}T12:00:00Z`)
  d.setUTCDate(d.getUTCDate() + offsetDays)
  return d.toISOString().slice(0, 10)
}
const TODAY = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Bishkek' }).format(new Date())

;(async () => {
  fs.rmSync(REC, { recursive: true, force: true })
  fs.mkdirSync(FRAMES, { recursive: true })
  const browser = await chromium.launch({ args: ['--lang=ru-RU'], env: { ...process.env, LANG: 'ru_RU.UTF-8', LANGUAGE: 'ru' } })
  const context = await browser.newContext({ viewport: VIEW, deviceScaleFactor: DPR, locale: 'ru-RU', timezoneId: 'Asia/Bishkek' })
  await context.addInitScript(cursorScript)
  const page = await context.newPage()

  const frames = []
  const events = []
  let offsets = []
  const cdp = await context.newCDPSession(page)
  cdp.on('Page.screencastFrame', async ({ data, metadata, sessionId }) => {
    const file = `${String(frames.length).padStart(6, '0')}.jpg`
    fs.writeFileSync(path.join(FRAMES, file), Buffer.from(data, 'base64'))
    frames.push({ file, ts: metadata.timestamp })
    offsets.push(now() - metadata.timestamp)
    try { await cdp.send('Page.screencastFrameAck', { sessionId }) } catch {}
  })

  // --- помощники ---------------------------------------------------------
  let mouse = { x: VIEW.width / 2, y: VIEW.height / 2 }
  const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2)
  async function moveTo(x, y, ms = 520) {
    const from = { ...mouse }
    const steps = Math.max(10, Math.round(ms / 16))
    for (let i = 1; i <= steps; i++) {
      const k = ease(i / steps)
      await page.mouse.move(from.x + (x - from.x) * k, from.y + (y - from.y) * k)
      await sleep(ms / steps)
    }
    mouse = { x, y }
  }
  async function center(loc) {
    await loc.waitFor({ state: 'visible', timeout: 10000 })
    await loc.scrollIntoViewIfNeeded()
    const b = await loc.boundingBox()
    return { x: b.x + b.width / 2, y: b.y + b.height / 2 }
  }
  async function hover(loc, ms) { const c = await center(loc); await moveTo(c.x, c.y, ms) }
  async function click(loc, ms) {
    const c = await center(loc)
    await moveTo(c.x, c.y, ms)
    await sleep(120)
    await page.mouse.down(); await sleep(70); await page.mouse.up()
    await sleep(250)
  }
  async function type(loc, text, delay = 45) { await click(loc); await loc.pressSequentially(text, { delay }) }
  async function select(loc, value) {
    await hover(loc, 480)
    await page.evaluate(({ x, y }) => window.__ripple && window.__ripple(x, y), mouse)
    await sleep(150)
    await loc.selectOption(value)
    await sleep(250)
  }
  async function fillField(loc, value) {
    await hover(loc, 480)
    await page.evaluate(({ x, y }) => window.__ripple && window.__ripple(x, y), mouse)
    await loc.fill(value)
    await sleep(300)
  }
  async function scrollTo(y, ms = 900) {
    await page.evaluate((top) => window.scrollTo({ top, behavior: 'smooth' }), y)
    await sleep(ms)
  }
  async function boxOf(locs, pad = 14) {
    const list = Array.isArray(locs) ? locs : [locs]
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity
    for (const l of list) {
      const b = await l.boundingBox()
      if (!b) continue
      x0 = Math.min(x0, b.x); y0 = Math.min(y0, b.y); x1 = Math.max(x1, b.x + b.width); y1 = Math.max(y1, b.y + b.height)
    }
    return { x: x0 - pad, y: y0 - pad, width: x1 - x0 + 2 * pad, height: y1 - y0 + 2 * pad }
  }
  // Приближение области (CSS-пиксели вьюпорта) на dur секунд.
  async function zoom(locs, dur, opts = {}) {
    const box = await boxOf(locs, opts.pad ?? 14)
    events.push({ type: 'zoom', t: now(), dur, box, max: opts.max ?? 2.0 })
  }
  // Поясняющая подпись поверх видео.
  function note(text, dur) { events.push({ type: 'note', t: now(), dur, text }) }

  const nav = (label) => page.locator('aside nav a', { hasText: label })
  const metric = (label) => page.locator('div.card', { has: page.locator('p', { hasText: new RegExp(`^${label}$`) }) }).first()
  const btn = (name) => page.getByRole('button', { name, exact: true })
  const seg = (name) => page.getByRole('radio', { name, exact: true })

  // --- сцены -------------------------------------------------------------
  const ACTIONS = {
    async login(at) {
      await at(0, 0.3)
      await type(page.locator('#username'), USER, 40)
      await type(page.locator('#password'), PASSWORD, 30)
      await at(1, 0.2)
      await click(page.locator('button[type=submit]'))
      await page.waitForURL('**/marketing')
      await page.locator('section[aria-label="Сводка"]').waitFor()
      await sleep(400)
      await moveTo(900, 420, 500)
    },
    async overview(at) {
      await at(0, 0.2)
      await zoom(page.locator('main section').first(), timing_of('overview', 0).duration + 0.2, { max: 1.9 })
      await at(1, 0.1)
      await zoom(page.locator('section[aria-label="Сводка"]'), timing_of('overview', 1).duration + 0.3, { max: 1.6 })
      await hover(metric('Просрочено'), 800)
      await sleep(900)
      await hover(metric('Опубликовано'), 800)
      await at(2, 0.3)
      note('Только данные из базы, без прогнозов. В видео — обезличенный демо-пример', timing_of('overview', 2).duration + 0.2)
      await at(3, 0.1)
      await click(btn('Предыдущий месяц'), 450)
      await sleep(900)
      await click(btn('Следующий месяц'))
      await at(4, 0.1)
      const work = page.locator('div.card', { hasText: 'Рабочий день' }).last()
      await zoom(work, timing_of('overview', 4).duration + 0.2, { max: 2.0 })
      await hover(work.locator('text=Приход').first(), 700)
      await at(5, 0)
      await moveTo(700, 600, 500)
      await scrollTo(420, 1200)
    },
    async content(at) {
      await at(0, 0)
      await click(nav('Контент-план'))
      await page.locator('text=Октябрь, text=Ноябрь').first().waitFor({ timeout: 3000 }).catch(() => {})
      await sleep(600)
      note('Идея → Подготовка → Согласование → Запланировано → Опубликовано', timing_of('content', 0).duration - 1.0)
      await at(1, 0.1)
      const items = page.locator('button[title]')
      const week = await items.nth(4).boundingBox()
      events.push({ type: 'zoom', t: now(), dur: timing_of('content', 1).duration + 0.2, box: { x: 272, y: week.y - 40, width: 1121, height: 120 }, max: 2.2 })
      await hover(items.nth(4), 700)
      await at(2, 0)
      await select(page.getByRole('combobox', { name: 'Канал' }), 'instagram')
      await sleep(1600)
      await select(page.getByRole('combobox', { name: 'Канал' }), '')
      await at(3, 0)
      const undated = page.locator('button', { hasText: 'Без даты' })
      await click(undated)
      await sleep(Math.max(500, (timing_of('content', 3).duration - 1.5) * 1000))
    },
    async create_content(at) {
      await at(0, 0)
      await click(btn('Новая публикация'))
      await sleep(400)
      await type(page.locator('#c-title'), 'Приглашение на открытый урок по Python', 26)
      await at(1, 0)
      await select(page.locator('#c-channel'), 'instagram')
      await select(page.locator('#c-format'), 'reels')
      await select(page.locator('#c-status'), 'preparing')
      const target = localISO(1).slice(0, 7) === TODAY.slice(0, 7) ? localISO(1) : TODAY
      await fillField(page.locator('#c-date'), target)
      await fillField(page.locator('#c-time'), '19:00')
      await at(2, 0)
      await zoom([page.locator('label[for="c-status"]'), page.locator('#c-time')], timing_of('create_content', 2).duration + 0.2, { max: 2.0, pad: 18 })
      await at(3, 0)
      await click(btn('Сохранить'))
      await sleep(900)
      const created = page.locator('button[title^="Приглашение на открытый урок"]').first()
      await zoom(created, 3.2, { max: 2.2, pad: 60 })
      await hover(created, 600)
    },
    async status(at) {
      await at(0, 0)
      const post = page.locator('button[title^="Объявление о старте новых групп"]').first()
      await click(post)
      await sleep(500)
      await select(page.locator('#c-status'), 'published')
      await at(1, 0)
      await type(page.locator('#c-url'), 'https://example.com/post', 40)
      await at(2, 0)
      await click(btn('Сохранить'))
      await sleep(600)
      note('Статус «Опубликовано» → пост засчитан в выполнение плана', timing_of('status', 2).duration)
    },
    async tasks(at) {
      await at(0, 0)
      await click(nav('Задачи'))
      await sleep(700)
      await at(1, 0)
      await zoom(page.locator('ul li').nth(0).locator('xpath=..'), timing_of('tasks', 1).duration + 0.2, { max: 1.7 })
      await hover(page.locator('text=Просрочено:').first(), 700)
      await at(2, 0)
      await click(seg('Просроченные'))
      await sleep(1100)
      await click(btn('Только мои'))
      await sleep(1000)
      await click(btn('Только мои'))
      await click(seg('Открытые'))
      await at(3, 0)
      await click(btn('Новая задача'))
      await sleep(300)
      await type(page.locator('#t-title'), 'Подготовить сторис с открытого урока', 32)
      await fillField(page.locator('#t-due'), localISO(2))
      await select(page.locator('#t-priority'), 'high')
      await click(btn('Сохранить'))
      await sleep(500)
      await at(4, 0)
      const done = btn('Отметить выполненной: Подготовить фото для поста о новых группах')
      await zoom(done.locator('xpath=ancestor::li[1]'), 3.0, { max: 1.8 })
      await click(done)
      await at(5, 0)
      note('Удалить запись может только её автор или администратор', timing_of('tasks', 5).duration)
    },
    async salary(at) {
      await at(0, 0)
      await click(nav('Моя зарплата'))
      await sleep(800)
      await hover(page.locator('h1', { hasText: 'Моя зарплата' }), 700)
    },
    async reports(at) {
      await at(0, 0)
      await click(nav('Отчёты'))
      await metric('Выполнение плана').waitFor()
      await sleep(500)
      await at(1, 0)
      await zoom(metric('Выполнение плана'), timing_of('reports', 1).duration + 0.2, { max: 2.2 })
      await hover(metric('Выполнение плана'), 600)
      await at(2, 0)
      await zoom([metric('Опубликовано'), metric('Выполнено задач')], timing_of('reports', 2).duration + 0.2, { max: 1.8 })
      await at(3, 0)
      const dyn = page.locator('div.card', { has: page.locator('h2', { hasText: 'Динамика' }) })
      await zoom(dyn, timing_of('reports', 3).duration * 0.45, { max: 1.8 })
      await hover(dyn, 600)
      await sleep(timing_of('reports', 3).duration * 450)
      const ch = page.locator('div.card', { has: page.locator('h2', { hasText: 'По каналам' }) })
      await zoom(ch, timing_of('reports', 3).duration * 0.5, { max: 1.8 })
      await hover(ch, 600)
      await at(4, 0)
      await moveTo(800, 500, 400)
      await scrollTo(700, 1300)
      await at(5, 0)
      await scrollTo(10000, 900)
      const foot = page.locator('p', { hasText: 'Заявки и рекламные кампании' }).first()
      await zoom(foot, timing_of('reports', 5).duration, { max: 2.6, pad: 18 })
      await hover(foot, 500)
      await at(6, 0)
      await scrollTo(0, 900)
      await click(seg('Неделя'))
      await sleep(900)
      await click(btn('Предыдущий период'))
    },
    async example(at) {
      await at(0, 0)
      await click(nav('Обзор'))
      await sleep(800)
      await zoom(metric('Просрочено'), timing_of('example', 0).duration - 0.6, { max: 2.4, pad: 30 })
      await hover(metric('Просрочено'), 600)
      await at(1, 0)
      await click(nav('Отчёты'))
      await metric('Выполнение плана').waitFor()
      await sleep(400)
      await zoom(metric('Выполнение плана'), timing_of('example', 1).duration - 0.7, { max: 2.4, pad: 30 })
      await at(2, 0)
      await click(nav('Контент-план'))
      await sleep(600)
      await click(seg('Список'))
      await sleep(500)
      await select(page.getByRole('combobox', { name: 'Статус' }), 'review')
      await sleep(700)
      await at(3, 0)
      const stuck = page.locator('button', { hasText: 'Знакомство с тренерами' }).first()
      await zoom(stuck.locator('xpath=ancestor::li[1]'), timing_of('example', 3).duration + 0.4, { max: 2.0 })
      await hover(stuck, 600)
      await at(4, 0)
      note('Согласовать и перенести пост · сменить срок или ответственного у просроченных задач', timing_of('example', 4).duration)
    },
  }

  // Подготовка перед сценой (вне кадра: переход в монтаже скрывает её).
  const PREP = {
    async create_content() {
      await select(page.getByRole('combobox', { name: 'Статус' }), '')
      await click(seg('Календарь'), 300)
      await page.locator('button[title]').first().waitFor()
    },
    async example() {
      await page.evaluate(() => window.scrollTo(0, 0))
    },
  }

  function timing_of(id, n) { return timing.scenes.find((s) => s.id === id).lines[n] }

  // --- подготовка (вне кадра) ----------------------------------------------
  await page.goto(`${APP}/login`)
  await page.locator('#username').waitFor()
  await page.mouse.move(mouse.x, mouse.y)
  await cdp.send('Page.startScreencast', { format: 'jpeg', quality: 98, maxWidth: VIEW.width * DPR, maxHeight: VIEW.height * DPR, everyNthFrame: 1 })
  await sleep(800)

  for (const scene of timing.scenes.filter((s) => s.kind === 'screen')) {
    if (scene.id === 'overview' || scene.id === 'reports') await page.evaluate(() => window.scrollTo(0, 0))
    if (PREP[scene.id]) await PREP[scene.id]()
    await sleep(300)
    const start = now()
    events.push({ type: 'scene', id: scene.id, t: start, dur: scene.duration })
    const at = async (n, extra = 0) => {
      const target = start + scene.lines[n].start + extra
      const wait = target - now()
      if (wait > 0) await sleep(wait * 1000)
      else if (wait < -0.3) console.warn(`  ! ${scene.id}: реплика ${n} — действия опаздывают на ${(-wait).toFixed(1)} c`)
    }
    process.stdout.write(`${scene.id} (${scene.duration.toFixed(1)} c)… `)
    try {
      await ACTIONS[scene.id](at)
    } catch (e) {
      await page.screenshot({ path: path.join(REC, `error-${scene.id}.png`) })
      throw e
    }
    const left = start + scene.duration - now()
    if (left < 0) console.warn(`\n  ! ${scene.id}: действия длиннее сцены на ${(-left).toFixed(1)} c`)
    else await sleep(left * 1000)
    console.log('ok')
  }
  await sleep(300)
  await cdp.send('Page.stopScreencast')
  offsets.sort((a, b) => a - b)
  const offset = offsets[Math.floor(offsets.length / 2)]
  fs.writeFileSync(path.join(REC, 'events.json'), JSON.stringify({ viewport: VIEW, dpr: DPR, clockOffset: offset, frames, events }, null, 1))
  console.log(`Кадров: ${frames.length}, событий: ${events.length}, смещение часов: ${offset.toFixed(3)} c`)
  await browser.close()
})().catch((e) => { console.error(e); process.exit(1) })
