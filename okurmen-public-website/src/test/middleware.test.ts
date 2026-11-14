/**
 * middleware.ts: live sitemap, real 404s, crawler metadata for detail pages.
 * (jsdom like the other suites; the middleware only uses fetch / Request / Response.)
 */
import middleware from '../../middleware'

const TEMPLATE = '<!doctype html><html lang="ru"><head><!--seo--><title>Home</title><!--/seo--></head><body><noscript><h1>Home</h1></noscript><div id="root"></div></body></html>'
const BOT = 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'
const API = 'https://api.test'

const DATA: Record<string, unknown> = {
  '/api/v1/public/site/sitemap/': { news: [{ slug: 'hello', updated_at: '2026-11-11T10:00:00Z' }] },
  '/api/v1/public/news/hello/?lang=ru': { title: '🚀 Привет', excerpt: 'Короткий текст.', published_at: '2026-11-11T10:00:00Z', cover: { url: '/media/n.webp' } },
  '/api/v1/public/news/hello/?lang=ky': { title: '🚀 Привет', excerpt: 'Короткий текст.', published_at: '2026-11-11T10:00:00Z', cover: null },
  '/api/v1/public/site/courses/python/?lang=ru': { title: 'Python', tagline: 'Курс', body: '' },
  '/api/v1/public/site/courses/python/?lang=ky': { title: 'Python', tagline: 'Курс ky', body: '' },
  '/api/v1/public/site/courses/python/?lang=en': { title: 'Python', tagline: 'Курс', body: '' },
}

beforeEach(() => {
  process.env.VITE_API_URL = API
  process.env.VITE_SITE_URL = 'https://www.okurmenkids.com'
  vi.stubGlobal('fetch', vi.fn(async (input: string | URL) => {
    const url = String(input)
    if (url.endsWith('/index.html')) return new Response(TEMPLATE)
    const key = url.replace(API, '')
    return key in DATA ? Response.json(DATA[key]) : new Response('{}', { status: 404 })
  }))
})
afterEach(() => vi.unstubAllGlobals())

const call = (path: string, ua = 'Mozilla/5.0 Chrome/130') => middleware(new Request(`https://www.okurmenkids.com${path}`, { headers: { 'user-agent': ua } }))
const passes = (response: Response) => response.headers.get('x-middleware-next') === '1'

describe('middleware', () => {
  it('lets static pages and app routes through to the built files', async () => {
    for (const path of ['/', '/ky', '/en/courses', '/news', '/enroll', '/preview/abc', '/courses/python']) expect(passes(await call(path)), path).toBe(true)
  })

  it('answers unknown URLs with a real 404 and noindex', async () => {
    for (const path of ['/nope', '/ky/nope', '/courses/a/b', '/admin']) {
      const response = await call(path)
      expect(response.status, path).toBe(404)
      const html = await response.text()
      expect(html).toContain('noindex')
      expect(html).not.toContain('<h1>Home</h1>')
    }
  })

  it('serves the live sitemap with content in its real languages', async () => {
    const response = await call('/sitemap.xml')
    expect(response.headers.get('content-type')).toContain('application/xml')
    const xml = await response.text()
    expect(xml).toContain('<loc>https://www.okurmenkids.com/news/hello</loc>')
    expect(xml).not.toContain('/ky/news/hello')
    expect(xml).toContain('<loc>https://www.okurmenkids.com/ky/about</loc>')
  })

  it('gives crawlers the item metadata; an untranslated copy points to the original', async () => {
    const html = await (await call('/ky/news/hello', BOT)).text()
    expect(html).toContain('<html lang="ky"')
    expect(html).toContain('<title>Привет — жаңылыктар | Okurmen Kids</title>')
    expect(html).toContain('<link rel="canonical" href="https://www.okurmenkids.com/news/hello" />')
    expect(html).not.toContain('hreflang')
    expect(html).toContain('<div id="root"><h1>🚀 Привет</h1>')
    expect(html).not.toContain('<h1>Home</h1>')
    expect(html).toContain('og:site_name" content="Okurmen Kids"')
    expect(html).not.toMatch(/digital/i)
  })

  it('lists only the real translations of a CMS item as hreflang', async () => {
    const html = await (await call('/courses/python', BOT)).text()
    expect(html).toContain('<link rel="canonical" href="https://www.okurmenkids.com/courses/python" />')
    expect(html).toContain('hreflang="ky"')
    expect(html).not.toContain('hreflang="en"')
  })

  it('answers 404 to crawlers for unpublished or deleted items', async () => {
    expect((await call('/news/gone', BOT)).status).toBe(404)
  })
})
