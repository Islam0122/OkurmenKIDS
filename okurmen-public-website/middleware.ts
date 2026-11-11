/**
 * Vercel Routing Middleware — SEO for crawlers that do not run JavaScript
 * (social previews: Facebook, Telegram, WhatsApp, X, LinkedIn; some search
 * bots). For them, detail pages get the real title, description, canonical
 * and Open Graph image, read from the same public API the React app uses.
 * Browsers and Google (which renders JS) get the normal SPA untouched.
 *
 * Env (Vercel project): VITE_API_URL, VITE_SITE_URL (and optionally VITE_MEDIA_URL).
 */
export const config = {
  matcher: ['/((?!assets/|api/|.*\\.[a-z0-9]+$).*)'],
}

const BOTS = /bot|crawl|spider|slurp|facebookexternalhit|facebot|twitterbot|telegrambot|whatsapp|linkedinbot|skypeuripreview|discordbot|vkshare|pinterest|embedly|quora link preview|redditbot|applebot|yandex/i

const DETAIL: Record<string, { api: (slug: string) => string; title: (d: any) => string; text: (d: any) => string; image: (d: any) => string | null | undefined }> = {
  courses: { api: (s) => `/api/v1/public/site/courses/${s}/`, title: (d) => d.title, text: (d) => d.tagline || d.body, image: (d) => d.cover?.url },
  events: { api: (s) => `/api/v1/public/site/events/${s}/`, title: (d) => d.title, text: (d) => d.excerpt || d.body, image: (d) => d.cover?.url },
  achievements: { api: (s) => `/api/v1/public/site/achievements/${s}/`, title: (d) => d.title, text: (d) => d.excerpt || d.body, image: (d) => d.cover?.url },
  news: { api: (s) => `/api/v1/public/news/${s}/`, title: (d) => d.title, text: (d) => d.excerpt || d.body, image: (d) => d.cover?.url },
  projects: { api: (s) => `/api/v1/public/projects/${s}/`, title: (d) => d.title, text: (d) => d.short_description || d.description, image: (d) => d.cover_url },
  team: { api: (s) => `/api/v1/public/site/team/${s}/`, title: (d) => `${d.name} — ${d.position}`, text: (d) => d.bio || d.position, image: (d) => d.photo?.url },
}

const escape = (s: string) => s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
const plain = (s: string) => (s || '').replace(/[#>*_`[\]()!]/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 200)
const next = () => new Response(null, { headers: { 'x-middleware-next': '1' } })

export default async function middleware(request: Request): Promise<Response> {
  if (!BOTS.test(request.headers.get('user-agent') || '')) return next()
  const url = new URL(request.url)
  const match = url.pathname.match(/^(?:\/(ky|en))?\/(courses|events|achievements|news|projects|team)\/([a-z0-9-]+)\/?$/i)
  const api = (process.env.VITE_API_URL || '').replace(/\/+$/, '')
  if (!match || !api) return next()
  const [, lang = 'ru', section, slug] = match
  const spec = DETAIL[section]
  try {
    const [page, data] = await Promise.all([
      fetch(new URL('/index.html', url)).then((r) => r.text()),
      fetch(`${api}${spec.api(slug)}?lang=${lang}`, { headers: { Accept: 'application/json' } }).then((r) => (r.ok ? r.json() : null)),
    ])
    if (!data) return next()
    const site = (process.env.VITE_SITE_URL || url.origin).replace(/\/+$/, '')
    const media = (process.env.VITE_MEDIA_URL || api).replace(/\/+$/, '')
    const rawImage = spec.image(data)
    const image = rawImage ? (rawImage.startsWith('http') ? rawImage : `${media}${rawImage}`) : `${site}/og-image.png`
    const title = `${spec.title(data)} — Okurmen Kids`
    const text = plain(spec.text(data))
    const canonical = `${site}${url.pathname.replace(/\/$/, '')}`
    const tags = [
      `<title>${escape(title)}</title>`,
      `<meta name="description" content="${escape(text)}" />`,
      `<link rel="canonical" href="${escape(canonical)}" />`,
      `<meta property="og:title" content="${escape(title)}" />`,
      `<meta property="og:description" content="${escape(text)}" />`,
      `<meta property="og:image" content="${escape(image)}" />`,
      `<meta property="og:url" content="${escape(canonical)}" />`,
      `<meta property="og:type" content="${section === 'news' ? 'article' : 'website'}" />`,
      `<meta name="twitter:card" content="summary_large_image" />`,
    ].join('\n    ')
    const html = page
      .replace(/<title>[\s\S]*?<\/title>/, '')
      .replace(/<meta (name="description"|property="og:[a-z]+"|name="twitter:card")[^>]*>\s*/g, '')
      .replace('</head>', `    ${tags}\n  </head>`)
      .replace('<div id="root"></div>', `<div id="root"><h1>${escape(spec.title(data))}</h1><p>${escape(text)}</p></div>`)
    return new Response(html, { headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'public, max-age=300' } })
  } catch {
    return next()
  }
}
