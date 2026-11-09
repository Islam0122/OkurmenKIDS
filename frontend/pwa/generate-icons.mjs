/**
 * Renders the PWA icon set and iOS splash screens into public/ from
 * pwa/badge.svg. Re-run only when the brand art changes:
 *
 *   node pwa/generate-icons.mjs
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
const badge = readFileSync(join(root, 'pwa/badge.svg'), 'utf8').replace(/<!--[\s\S]*?-->/g, '')
const font = (subset) =>
  readFileSync(join(root, `node_modules/@fontsource-variable/manrope/files/manrope-${subset}-wght-normal.woff2`)).toString('base64')

const FONT_CSS = ['latin', 'cyrillic']
  .map((s) => `@font-face{font-family:'Manrope Variable';font-weight:200 800;src:url(data:font/woff2;base64,${font(s)}) format('woff2')}`)
  .join('')

const BRAND_GRADIENT = `<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
  <stop offset="0" stop-color="#34a065"/><stop offset="1" stop-color="#1f5f3c"/></linearGradient></defs>`

/** «any»: a rounded tile with a transparent margin (desktop docks, Windows). */
const anySvg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">${BRAND_GRADIENT}
  <rect x="20" y="20" width="472" height="472" rx="108" fill="url(#g)"/>
  <g transform="translate(256 256) scale(0.98) translate(-256 -256)">${badge}</g></svg>`

/** «maskable» / Apple touch: full bleed, the badge inside the 80% safe circle. */
const fullSvg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">${BRAND_GRADIENT}
  <rect width="512" height="512" fill="url(#g)"/>
  <g transform="translate(256 256) scale(0.9) translate(-256 -256)">${badge}</g></svg>`

const ICONS = [
  { file: 'icons/icon-192.png', svg: anySvg, size: 192 },
  { file: 'icons/icon-512.png', svg: anySvg, size: 512 },
  { file: 'icons/maskable-192.png', svg: fullSvg, size: 192 },
  { file: 'icons/maskable-512.png', svg: fullSvg, size: 512 },
  { file: 'icons/apple-touch-icon.png', svg: fullSvg, size: 180 },
]

/** iOS launch images (portrait, CSS px × DPR) — see index.html media queries. */
export const SPLASH = [
  [430, 932, 3], [393, 852, 3], [428, 926, 3], [390, 844, 3], [375, 812, 3], [414, 896, 3],
  [414, 896, 2], [375, 667, 2], [402, 874, 3], [440, 956, 3],
  [820, 1180, 2], [834, 1194, 2], [1024, 1366, 2], [810, 1080, 2],
]

const browser = await chromium.launch()
const page = await browser.newPage()

for (const { file, svg, size } of ICONS) {
  await page.setViewportSize({ width: size, height: size })
  await page.setContent(`<style>${FONT_CSS}html,body{margin:0;background:transparent}svg{display:block;width:${size}px;height:${size}px}</style>${svg}`)
  await page.evaluate(() => document.fonts.ready)
  await page.screenshot({ path: join(root, 'public', file), omitBackground: true })
  console.log('wrote', file)
}

for (const [w, h, dpr] of SPLASH) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: dpr })
  const p = await ctx.newPage()
  const icon = Math.round(Math.min(w, h) * 0.34)
  await p.setContent(`<style>${FONT_CSS}
    html,body{margin:0;height:100%;background:#f7f9f7;font-family:'Manrope Variable',sans-serif}
    body{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:${Math.round(icon * 0.14)}px}
    svg{width:${icon}px;height:${icon}px;filter:drop-shadow(0 12px 28px rgba(31,95,60,.22))}
    p{margin:0;font-weight:800;font-size:${Math.round(icon * 0.15)}px;color:#202622;letter-spacing:-.01em}
    p span{color:#2f8f5b}</style>${anySvg}<p>Okurmen <span>Kids</span></p>`)
  await p.evaluate(() => document.fonts.ready)
  const file = `splash/apple-splash-${w * dpr}x${h * dpr}.png`
  await p.screenshot({ path: join(root, 'public', file) })
  await ctx.close()
  console.log('wrote', file)
}

await browser.close()
