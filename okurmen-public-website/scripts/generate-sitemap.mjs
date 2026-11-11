#!/usr/bin/env node
/**
 * Build step: writes dist/sitemap.xml (all ten sections + every published
 * course, project, news article, event and achievement, in ru/ky/en with
 * hreflang alternates) and an absolute Sitemap line in dist/robots.txt.
 *
 * Content URLs come from GET {VITE_API_URL}/api/v1/public/site/sitemap/. If
 * the API is unreachable at build time the static pages are still written —
 * the build never fails because of it.
 */
import { readFileSync, writeFileSync, existsSync } from 'node:fs'
import { resolve } from 'node:path'

const env = { ...process.env }
for (const file of ['.env', '.env.production', '.env.local', '.env.production.local']) {
  const path = resolve(file)
  if (!existsSync(path)) continue
  for (const line of readFileSync(path, 'utf8').split('\n')) {
    const match = line.match(/^\s*([A-Z_]+)\s*=\s*(.*)\s*$/)
    if (match && env[match[1]] === undefined) env[match[1]] = match[2].replace(/^['"]|['"]$/g, '')
  }
}

const site = (env.VITE_SITE_URL || '').replace(/\/+$/, '')
const api = (env.VITE_API_URL || '').replace(/\/+$/, '')
const dist = resolve('dist')
if (!site) {
  console.warn('[sitemap] VITE_SITE_URL is not set — sitemap.xml skipped.')
  process.exit(0)
}

const LANGS = ['ru', 'ky', 'en']
const localized = (lang, path) => (lang === 'ru' ? path : path === '/' ? `/${lang}` : `/${lang}${path}`)
const STATIC = ['/', '/about', '/courses', '/projects', '/achievements', '/news', '/events', '/team', '/testimonials', '/contacts']

const entries = STATIC.map((path) => ({ path, lastmod: null, priority: path === '/' ? '1.0' : '0.8', changefreq: 'weekly' }))

if (api) {
  try {
    const response = await fetch(`${api}/api/v1/public/site/sitemap/`, { signal: AbortSignal.timeout(15000) })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const data = await response.json()
    const add = (items, prefix, priority) => {
      for (const item of items ?? []) entries.push({ path: `${prefix}/${item.slug}`, lastmod: item.updated_at?.slice(0, 10) ?? null, priority, changefreq: 'monthly' })
    }
    add(data.courses, '/courses', '0.9')
    add(data.events, '/events', '0.7')
    add(data.news, '/news', '0.7')
    add(data.projects, '/projects', '0.6')
    add(data.achievements, '/achievements', '0.6')
    add(data.team, '/team', '0.5')
    console.log(`[sitemap] ${entries.length - STATIC.length} content pages from the API`)
  } catch (error) {
    console.warn(`[sitemap] API unreachable (${error.message}) — static pages only.`)
  }
}

const xmlEscape = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
const urls = entries.flatMap((entry) =>
  LANGS.map((lang) => {
    const alternates = [...LANGS.map((l) => [l, localized(l, entry.path)]), ['x-default', entry.path]]
      .map(([l, p]) => `    <xhtml:link rel="alternate" hreflang="${l}" href="${xmlEscape(site + p)}"/>`)
      .join('\n')
    return [
      '  <url>',
      `    <loc>${xmlEscape(site + localized(lang, entry.path))}</loc>`,
      entry.lastmod ? `    <lastmod>${entry.lastmod}</lastmod>` : null,
      `    <changefreq>${entry.changefreq}</changefreq>`,
      `    <priority>${entry.priority}</priority>`,
      alternates,
      '  </url>',
    ].filter(Boolean).join('\n')
  }),
)

writeFileSync(
  resolve(dist, 'sitemap.xml'),
  `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">\n${urls.join('\n')}\n</urlset>\n`,
)
const robots = resolve(dist, 'robots.txt')
if (existsSync(robots)) writeFileSync(robots, readFileSync(robots, 'utf8').replace(/^Sitemap:.*$/m, `Sitemap: ${site}/sitemap.xml`))
console.log(`[sitemap] wrote ${urls.length} URLs to dist/sitemap.xml`)
