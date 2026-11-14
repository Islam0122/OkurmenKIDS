#!/usr/bin/env node
/**
 * Build step: one HTML file per static page and language
 * (dist/index.html, dist/about/index.html, dist/ky/courses/index.html, …)
 * with that page's own <title>, description, robots, canonical, hreflang,
 * Open Graph / Twitter tags, JSON-LD and <html lang>, plus a <noscript> H1,
 * description and section links. Every crawler — including the ones that do
 * not run JavaScript — gets correct metadata in the raw HTML; people get the
 * same file and the React app renders on top of it as before.
 *
 * Detail pages (courses/:slug, news/:slug …) are served by the SPA fallback;
 * crawlers get their tags live from middleware.ts. Same source for all:
 * src/seo/core.js.
 */
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'

import { breadcrumbLd, LANGS, localized, noscriptBody, organizationLd, pageSeo, renderPage, sectionCrumbs, STATIC_PATHS, websiteLd } from '../src/seo/core.js'
import { fetchJson, loadEnv } from './env.mjs'

const { site, api } = loadEnv()
const dist = resolve('dist')
const template = readFileSync(resolve(dist, 'index.html'), 'utf8')

const settings = {}
await Promise.all(LANGS.map(async (lang) => {
  if (!api) return
  settings[lang] = await fetchJson(`${api}/api/v1/public/site/settings/?lang=${lang}`).catch((error) => {
    console.warn(`[prerender] settings (${lang}) unavailable: ${error.message} — Organization without contacts.`)
    return null
  })
}))

let written = 0
for (const lang of LANGS) {
  for (const path of STATIC_PATHS) {
    const seo = pageSeo(lang, path)
    const section = path.slice(1)
    const jsonLd = path === '/'
      ? [organizationLd(site, lang, settings[lang]), websiteLd(site, lang)]
      : [
          ...(path === '/about' || path === '/contacts' ? [organizationLd(site, lang, settings[lang])] : []),
          breadcrumbLd(site, sectionCrumbs(lang, section)),
        ]
    const html = renderPage(template, { site, lang, path, title: seo.title, description: seo.description, jsonLd }, noscriptBody(lang, seo.title.replace(/\s+[—|]\s+Okurmen Kids$/, ''), seo.description))
    const url = localized(lang, path)
    const file = url === '/' ? resolve(dist, 'index.html') : resolve(dist, `.${url}`, 'index.html')
    mkdirSync(dirname(file), { recursive: true })
    writeFileSync(file, html)
    written++
  }
}
console.log(`[prerender] wrote ${written} static pages with their own SEO tags (${site})`)
