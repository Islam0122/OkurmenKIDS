/**
 * Vercel Routing Middleware — SEO that a client-rendered SPA cannot do alone.
 *
 * 1. /sitemap.xml is generated live from the published CMS content, so it
 *    changes as soon as an item is published or removed (no redeploy). If the
 *    API is down, the sitemap built at deploy time (dist/sitemap.xml) is served.
 * 2. Unknown URLs get a real HTTP 404 (the SPA still renders its «not found»
 *    page) instead of a «soft 404» with status 200.
 * 3. Crawlers (search and social bots — Google, Yandex, Telegram, WhatsApp,
 *    Facebook, X …) get detail pages with the real title, description,
 *    canonical, hreflang, Open Graph and the item's heading and text in the
 *    HTML, read from the same public API the app uses. Unpublished or deleted
 *    items answer 404. Static pages already have their tags in the built HTML
 *    (scripts/prerender-seo.mjs). Everything comes from src/seo/core.js —
 *    the same code the React app uses, so bots and people see the same page.
 *
 * Env (Vercel project): VITE_API_URL (and optionally VITE_SITE_URL, VITE_MEDIA_URL).
 */
import {
  breadcrumbLd,
  canonicalPath,
  DETAIL,
  detailDescription,
  detailTitle,
  LANGS,
  renderPage,
  sectionCrumbs,
  SITE_ORIGIN,
  sitemapEntries,
  sitemapXml,
  splitLang,
  STATIC_PATHS,
  translatedLangs,
  type Lang,
  type Section,
} from './src/seo/core.js'

export const config = {
  matcher: ['/sitemap.xml', '/((?!assets/|api/|.*\\.[a-z0-9]+$).*)'],
}

const BOTS = /bot|crawl|spider|slurp|facebookexternalhit|facebot|twitterbot|telegrambot|whatsapp|linkedinbot|skypeuripreview|discordbot|vkshare|pinterest|embedly|quora link preview|redditbot|applebot|yandex|bingpreview|google-inspectiontool|lighthouse/i
const SECTIONS = Object.keys(DETAIL) as Section[]
/** Client routes that are not SEO pages but must not 404 (see src/app/router/routes.tsx). */
const UTILITY = /^\/(?:enroll|preview\/[^/]+)$/

const next = () => new Response(null, { headers: { 'x-middleware-next': '1' } })
const env = (name: string) => (process.env[name] || '').replace(/\/+$/, '')
const escapeHtml = (s: string) => s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

async function fetchJson(url: string): Promise<any> {
  const response = await fetch(url, { headers: { Accept: 'application/json' }, signal: AbortSignal.timeout(8000) })
  if (response.status === 404) return null
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return response.json()
}

/* The live sitemap is kept for a few minutes per edge instance. */
let sitemapCache: { xml: string; at: number } | null = null
const SITEMAP_TTL = 10 * 60_000

async function sitemap(site: string, api: string): Promise<Response> {
  if (!sitemapCache || Date.now() - sitemapCache.at > SITEMAP_TTL) {
    const { entries } = await sitemapEntries(api, fetchJson)
    sitemapCache = { xml: sitemapXml(site, entries), at: Date.now() }
  }
  return new Response(sitemapCache.xml, {
    headers: { 'content-type': 'application/xml; charset=utf-8', 'cache-control': 'public, max-age=600' },
  })
}

async function notFound(url: URL, lang: Lang): Promise<Response> {
  const template = await fetch(new URL('/index.html', url)).then((r) => r.text())
  const html = template
    .replace(/<html lang="[^"]*"/, `<html lang="${lang}"`)
    .replace(/<!--seo-->[\s\S]*?<!--\/seo-->/, '<title>404 — Okurmen Kids</title>\n    <meta name="robots" content="noindex, follow" />')
    .replace(/<noscript>[\s\S]*?<\/noscript>/, '')
  return new Response(html, { status: 404, headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'public, max-age=60' } })
}

export default async function middleware(request: Request): Promise<Response> {
  const url = new URL(request.url)
  const site = env('VITE_SITE_URL') || SITE_ORIGIN
  const api = env('VITE_API_URL')
  const isBot = BOTS.test(request.headers.get('user-agent') || '')

  try {
    if (url.pathname === '/sitemap.xml') return api ? await sitemap(site, api) : next()

    const { lang, rest } = splitLang(url.pathname)
    const path = canonicalPath(rest)
    if (STATIC_PATHS.includes(path) || UTILITY.test(path)) return next()

    const match = path.match(/^\/([a-z]+)\/([a-z0-9-]+)$/)
    const section = match?.[1] as Section | undefined
    if (!match || !section || !SECTIONS.includes(section)) return await notFound(url, lang)
    if (!isBot || !api) return next()

    const slug = match[2]
    const spec = DETAIL[section]
    const others = spec.fields ? LANGS.filter((code) => code !== lang) : []
    const [template, data, ...versions] = await Promise.all([
      fetch(new URL('/index.html', url)).then((r) => r.text()),
      fetchJson(`${api}${spec.api(slug)}?lang=${lang}`),
      ...others.map((code) => fetchJson(`${api}${spec.api(slug)}?lang=${code}`).catch(() => null)),
    ])
    if (!data) return await notFound(url, lang)

    const langs = spec.fields
      ? translatedLangs(section, Object.fromEntries([[lang, data], ...others.map((code, i) => [code, versions[i]])]))
      : (['ru'] as Lang[])
    const media = env('VITE_MEDIA_URL') || api
    const rawImage = spec.image(data)
    const image = rawImage ? (rawImage.startsWith('http') ? rawImage : `${media}${rawImage}`) : null
    const name = spec.name(data)
    const title = detailTitle(lang, section, name, data.seo_title, spec.subtitle?.(data))
    const description = detailDescription(lang, section, spec.text(data, lang), data.seo_description)
    const crumbName = section === 'team' ? data.name : name

    const html = renderPage(
      template,
      {
        site,
        lang,
        path,
        title,
        description,
        image,
        type: section === 'news' || section === 'achievements' ? 'article' : 'website',
        langs,
        publishedAt: section === 'news' ? data.published_at : null,
        jsonLd: breadcrumbLd(site, sectionCrumbs(lang, section, { name: crumbName, slug })),
      },
      '', // the page's own H1 and text go into #root below — not a second H1 in <noscript>
    ).replace('<div id="root"></div>', `<div id="root"><h1>${escapeHtml(name)}</h1><p>${escapeHtml(description)}</p></div>`)
    return new Response(html, { headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'public, max-age=300' } })
  } catch {
    return next()
  }
}
