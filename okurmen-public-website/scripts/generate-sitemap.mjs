#!/usr/bin/env node
/**
 * Build step: writes dist/sitemap.xml — every static page in ru/ky/en plus
 * every published course, project, news article, event, achievement and
 * team page in the languages it really exists in (hreflang alternates only
 * between real translations) — and the absolute Sitemap line in robots.txt.
 *
 * In production /sitemap.xml is generated live by middleware.ts (same code,
 * src/seo/core.js), so it follows publishing and deletion without a redeploy.
 * This file is the fallback the middleware serves when the API is down.
 * If the API is unreachable at build time, the static pages are still written.
 */
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { sitemapEntries, sitemapXml } from '../src/seo/core.js'
import { fetchJson, loadEnv } from './env.mjs'

const { site, api } = loadEnv()
const dist = resolve('dist')

let entries
try {
  const result = await sitemapEntries(api, fetchJson)
  entries = result.entries
  console.log(api ? `[sitemap] ${result.content} content pages from the API` : '[sitemap] VITE_API_URL is not set — static pages only.')
} catch (error) {
  console.warn(`[sitemap] API unreachable (${error.message}) — static pages only.`)
  entries = (await sitemapEntries('', fetchJson)).entries
}

const xml = sitemapXml(site, entries)
writeFileSync(resolve(dist, 'sitemap.xml'), xml)
const robots = resolve(dist, 'robots.txt')
if (existsSync(robots)) writeFileSync(robots, readFileSync(robots, 'utf8').replace(/^Sitemap:.*$/m, `Sitemap: ${site}/sitemap.xml`))
console.log(`[sitemap] wrote ${(xml.match(/<loc>/g) || []).length} URLs to dist/sitemap.xml (${site})`)
