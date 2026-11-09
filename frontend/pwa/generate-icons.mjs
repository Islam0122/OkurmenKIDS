/**
 * Renders the PWA icon set and iOS splash screens into public/ from
 * pwa/logo.svg. Re-run only when the brand art changes:
 *
 *   node pwa/generate-icons.mjs
 *
 * Design: a pure white, fully opaque square (corners included) with only the
 * Okurmen Kids logo (gold ring, violet glasses and «KIDS», gold «ОКУРМЭН»),
 * measured and centred exactly. The same image is used for «any»,
 * «maskable» and the Apple touch icon: the ring's outer diameter is 78% of
 * the icon, inside the 80% maskable safe circle, so Android launcher masks,
 * the macOS/iOS rounded squares and Chrome's install UI never clip it.
 *
 * Needs Playwright with Chromium (`npx playwright install chromium` if it is
 * not on the machine). Not part of `npm run build`: the PNGs are committed.
 */
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const { chromium } = require('playwright')

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const mark = readFileSync(join(root, 'pwa/logo.svg'), 'utf8').replace(/<!--[\s\S]*?-->/g, '')
const font = (subset) =>
  readFileSync(join(root, `node_modules/@fontsource-variable/manrope/files/manrope-${subset}-wght-normal.woff2`)).toString('base64')

const FONT_CSS = ['latin', 'cyrillic']
  .map((s) => `@font-face{font-family:'Manrope Variable';font-weight:200 800;src:url(data:font/woff2;base64,${font(s)}) format('woff2')}`)
  .join('')

const WHITE = '#ffffff'
/** Ring's outer diameter as a share of the icon: inside the maskable safe zone. */
const LOGO_WIDTH = 0.78

const ICONS = [
  { file: 'icons/icon-192.png', size: 192 },
  { file: 'icons/icon-512.png', size: 512 },
  { file: 'icons/maskable-192.png', size: 192 },
  { file: 'icons/maskable-512.png', size: 512 },
  { file: 'icons/apple-touch-icon.png', size: 180 },
]

/** iOS launch images (portrait, CSS px × DPR) — see index.html media queries. */
export const SPLASH = [
  [430, 932, 3], [393, 852, 3], [428, 926, 3], [390, 844, 3], [375, 812, 3], [414, 896, 3],
  [414, 896, 2], [375, 667, 2], [402, 874, 3], [440, 956, 3],
  [820, 1180, 2], [834, 1194, 2], [1024, 1366, 2], [810, 1080, 2],
]

/** A white canvas w×h with the logo centred at `logoWidth` px wide. */
function page(w, h, logoWidth) {
  return `<style>${FONT_CSS}html,body{margin:0;background:${WHITE}}svg{display:block}</style>
<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
  <rect width="${w}" height="${h}" fill="${WHITE}"/>
  <g id="place" data-w="${w}" data-h="${h}" data-logo="${logoWidth}"><g id="mark">${mark}</g></g>
</svg>`
}

/** Centre by the real rendered bounds (glyphs included), not by eye. */
async function centre(p) {
  await p.evaluate(async () => {
    await document.fonts.ready
    const place = document.getElementById('place')
    const box = document.getElementById('mark').getBBox()
    const { w, h, logo } = place.dataset
    const scale = Number(logo) / box.width
    const x = Number(w) / 2 - (box.x + box.width / 2) * scale
    const y = Number(h) / 2 - (box.y + box.height / 2) * scale
    place.setAttribute('transform', `translate(${x} ${y}) scale(${scale})`)
  })
}

/** Second pass: the text box is not the ink — shift by what the pixels say. */
async function centreOnInk(p) {
  const png = (await p.screenshot()).toString('base64')
  await p.evaluate(async (data) => {
    const img = new Image()
    img.src = `data:image/png;base64,${data}`
    await img.decode()
    const canvas = Object.assign(document.createElement('canvas'), { width: img.width, height: img.height })
    const ctx = canvas.getContext('2d')
    ctx.drawImage(img, 0, 0)
    const { data: px } = ctx.getImageData(0, 0, img.width, img.height)
    let x0 = img.width, y0 = img.height, x1 = 0, y1 = 0
    for (let y = 0; y < img.height; y += 1) {
      for (let x = 0; x < img.width; x += 1) {
        const i = (y * img.width + x) * 4
        if (px[i] < 245 || px[i + 1] < 245 || px[i + 2] < 245) {
          x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y)
        }
      }
    }
    // Screenshot pixels → CSS px (device scale factor).
    const ratio = img.width / window.innerWidth
    const dx = (img.width / 2 - (x0 + x1 + 1) / 2) / ratio
    const dy = (img.height / 2 - (y0 + y1 + 1) / 2) / ratio
    const place = document.getElementById('place')
    place.setAttribute('transform', `translate(${dx} ${dy}) ${place.getAttribute('transform')}`)
  }, png)
}

const browser = await chromium.launch()

for (const { file, size } of ICONS) {
  const p = await browser.newPage({ viewport: { width: size, height: size } })
  await p.setContent(page(size, size, size * LOGO_WIDTH))
  await centre(p)
  await centreOnInk(p)
  // Opaque PNG: white right into the corners, no transparency anywhere.
  await p.screenshot({ path: join(root, 'public', file), omitBackground: false })
  await p.close()
  console.log('wrote', file)
}

for (const [w, h, dpr] of SPLASH) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: dpr })
  const p = await ctx.newPage()
  await p.setContent(page(w, h, Math.round(Math.min(w, h) * 0.5)))
  await centre(p)
  await centreOnInk(p)
  const file = `splash/apple-splash-${w * dpr}x${h * dpr}.png`
  await p.screenshot({ path: join(root, 'public', file) })
  await ctx.close()
  console.log('wrote', file)
}

await browser.close()
