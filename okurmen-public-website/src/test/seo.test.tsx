import { readFileSync } from 'node:fs'

import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { Seo } from '@/components/shared/Seo'
import { I18nProvider } from '@/i18n'
import { en } from '@/i18n/locales/en'
import { ky } from '@/i18n/locales/ky'
import { ru } from '@/i18n/locales/ru'
import {
  BRAND,
  LOGO,
  canonicalPath,
  detailDescription,
  detailTitle,
  headTags,
  LANGS,
  openingHours,
  organizationLd,
  PAGES,
  projectText,
  sitemapEntries,
  sitemapXml,
  STATIC_PATHS,
  translatedLangs,
  websiteLd,
  type Lang,
} from '@/seo/core'
import { BRAND as APP_BRAND } from '@/app/config/site'

const SITE = 'https://www.okurmenkids.com'
const DICTS = { ru, ky, en } as const

describe('public brand', () => {
  it('is «OKURMEN Kids» everywhere public — no «Digital» in any page copy or UI string', () => {
    expect(BRAND).toBe('OKURMEN Kids')
    expect(APP_BRAND.name).toBe('OKURMEN Kids')
    expect(JSON.stringify(PAGES)).not.toMatch(/digital/i)
    for (const dict of Object.values(DICTS)) {
      for (const [key, value] of Object.entries(dict)) {
        if (key === 'icon.digital') expect(value).not.toMatch(/digital/i) // the key is an internal enum, the label is public
        else expect(`${key}: ${value}`).not.toMatch(/: .*digital/i)
      }
    }
    expect(JSON.stringify(organizationLd(SITE, 'ru', null))).not.toMatch(/digital/i)
    expect(JSON.stringify(websiteLd(SITE, 'en'))).not.toMatch(/digital/i)
  })
})

describe('static page metadata', () => {
  it('has a unique title (50–60 chars) and description (140–160 chars) for every page and language', () => {
    const titles = new Set<string>()
    const descriptions = new Set<string>()
    for (const lang of LANGS) {
      for (const path of STATIC_PATHS) {
        const { title, description } = PAGES[lang][path]
        expect(title.length, `${lang} ${path} title`).toBeGreaterThanOrEqual(50)
        expect(title.length, `${lang} ${path} title`).toBeLessThanOrEqual(60)
        expect(description.length, `${lang} ${path} description`).toBeGreaterThanOrEqual(140)
        expect(description.length, `${lang} ${path} description`).toBeLessThanOrEqual(160)
        expect(title).toContain(BRAND)
        titles.add(title)
        descriptions.add(description)
      }
    }
    expect(titles.size).toBe(LANGS.length * STATIC_PATHS.length)
    expect(descriptions.size).toBe(LANGS.length * STATIC_PATHS.length)
  })

  it('uses the navigation labels as breadcrumb names', () => {
    const NAV_KEY: Record<string, keyof typeof ru> = { '/': 'nav.home', '/about': 'nav.about', '/courses': 'nav.courses', '/projects': 'nav.projects', '/achievements': 'nav.achievements', '/news': 'nav.news', '/events': 'nav.events', '/team': 'nav.team', '/testimonials': 'nav.testimonials', '/contacts': 'nav.contacts' }
    for (const lang of LANGS) for (const path of STATIC_PATHS) expect(PAGES[lang][path].name).toBe(DICTS[lang][NAV_KEY[path]])
  })
})

describe('detail page metadata', () => {
  it('builds a branded, length-bounded title from the item', () => {
    expect(detailTitle('ru', 'courses', 'Премиум')).toBe('Премиум — курс для детей в Бишкеке | OKURMEN Kids')
    expect(detailTitle('ru', 'news', '🚀 Ученики OKURMEN Kids посетили Ololo!')).toBe('Ученики OKURMEN Kids посетили Ololo! — новости | OKURMEN Kids')
    const long = detailTitle('ru', 'news', 'Благодарственные письма родителям лучших учеников академии за отличную учёбу в октябре')
    expect(long.length).toBeLessThanOrEqual(70)
    expect(long.endsWith('— новости | OKURMEN Kids')).toBe(true)
    expect(detailTitle('ky', 'courses', 'X', 'SEO заголовок')).toBe('SEO заголовок — OKURMEN Kids')
  })

  it('gives an item with the same name a different title in every language', () => {
    for (const section of ['courses', 'events', 'achievements', 'team', 'news', 'projects'] as const) {
      for (const name of ['OKURMEN Kids Club — NEXT', 'Нурсултан Караталов — IT-тренер', 'А'.repeat(90)]) {
        const titles = LANGS.map((lang) => detailTitle(lang, section, name))
        expect(new Set(titles).size, `${section} ${name.slice(0, 20)}`).toBe(3)
        for (const title of titles) expect(title.length).toBeLessThanOrEqual(70)
      }
    }
  })

  it('tells student projects with the same name apart by their own description and lists real technologies', () => {
    const a = { title: 'ShopVerce', short_description: 'Магазин электроники и техники', technologies: ['React HTML CSS JavaScript'] }
    const b = { title: 'ShopVerce', short_description: 'Магазин электроники и гаджетов', technologies: ['HTML CSS JS', 'React'] }
    expect(detailTitle('ru', 'projects', a.title, null, a.short_description)).toBe('ShopVerce — Магазин электроники и техники | OKURMEN Kids')
    expect(detailTitle('ru', 'projects', b.title, null, b.short_description)).not.toBe(detailTitle('ru', 'projects', a.title, null, a.short_description))
    expect(projectText(b, 'ru')).toBe('Магазин электроники и гаджетов. Технологии: HTML, CSS, JS, React')
  })

  it('uses the item text for the description, padding a short one with a fact about the section', () => {
    expect(detailDescription('ru', 'projects', 'Интернет-магазин на React.')).toBe('Интернет-магазин на React. Проект ученика IT-академии OKURMEN Kids в Бишкеке.')
    const long = detailDescription('ru', 'news', '**Жирный** текст '.repeat(30))
    expect(long.length).toBeLessThanOrEqual(160)
    expect(long).not.toMatch(/\*/)
  })
})

describe('languages of CMS items', () => {
  const ru = { title: 'Стипендия', excerpt: 'Лучшая группа', body: 'Текст' }
  it('counts a language only when it really differs from the Russian fallback', () => {
    expect(translatedLangs('achievements', { ru, ky: { ...ru }, en: { ...ru, title: 'Scholarship' } })).toEqual(['ru', 'en'])
    expect(translatedLangs('achievements', { ru, ky: ru, en: ru })).toEqual(['ru'])
  })
  it('treats news and student projects as Russian-only', () => {
    expect(translatedLangs('news', { ru, ky: { title: 'другое' }, en: ru })).toEqual(['ru'])
    expect(translatedLangs('projects', { ru })).toEqual(['ru'])
  })
})

describe('canonical and hreflang', () => {
  it('normalizes the path', () => {
    expect(canonicalPath('/Courses/')).toBe('/courses')
    expect(canonicalPath('/news/abc?page=2#x')).toBe('/news/abc')
    expect(canonicalPath('/')).toBe('/')
  })

  it('lists only real translations and points an untranslated copy at the original', () => {
    const base = { site: SITE, path: '/news/x', title: 'T', description: 'D' }
    const ky = headTags({ ...base, lang: 'ky', langs: ['ru'] })
    expect(ky).toContain('<link rel="canonical" href="https://www.okurmenkids.com/news/x" />')
    expect(ky).not.toContain('hreflang')
    const all = headTags({ ...base, path: '/courses', lang: 'en' })
    expect(all).toContain('<link rel="canonical" href="https://www.okurmenkids.com/en/courses" />')
    for (const code of ['ru', 'ky', 'en', 'x-default']) expect(all).toContain(`hreflang="${code}"`)
    expect(all).toContain('<meta property="og:site_name" content="OKURMEN Kids" />')
    expect(all).toContain('index, follow')
  })

  it('sets the same tags in the browser (Seo component)', () => {
    const renderAt = (url: string, lang: Lang, langs?: Lang[] | null) => render(
      <MemoryRouter initialEntries={[url]}>
        <I18nProvider lang={lang}><Seo title="Новость | OKURMEN Kids" description="Описание" langs={langs} /></I18nProvider>
      </MemoryRouter>,
    )
    renderAt('/ky/news/x/', 'ky', ['ru'])
    expect(document.title).toBe('Новость | OKURMEN Kids')
    expect(document.documentElement.lang).toBe('ky')
    expect(document.head.querySelector('link[rel="canonical"]')?.getAttribute('href')).toBe('https://kids.test/news/x')
    expect(document.head.querySelectorAll('link[hreflang]')).toHaveLength(0)
    expect(document.head.querySelector('meta[property="og:site_name"]')?.getAttribute('content')).toBe('OKURMEN Kids')

    renderAt('/en/courses', 'en')
    expect(document.head.querySelector('link[rel="canonical"]')?.getAttribute('href')).toBe('https://kids.test/en/courses')
    expect([...document.head.querySelectorAll('link[hreflang]')].map((el) => el.getAttribute('hreflang'))).toEqual(['ru', 'ky', 'en', 'x-default'])
  })

  it('uses the static page copy for a page by path', () => {
    render(<MemoryRouter initialEntries={['/ky/events']}><I18nProvider lang="ky"><Seo page="/events" /></I18nProvider></MemoryRouter>)
    expect(document.title).toBe(PAGES.ky['/events'].title)
    expect(document.head.querySelector('meta[name="description"]')?.getAttribute('content')).toBe(PAGES.ky['/events'].description)
  })
})

describe('sitemap', () => {
  it('has static pages in all languages and items only in their real languages', async () => {
    const api = 'https://api.test'
    const records: Record<string, unknown> = {
      [`${api}/api/v1/public/site/sitemap/`]: { courses: [{ slug: 'python', updated_at: '2026-11-01T10:00:00Z' }], news: [{ slug: 'hello', updated_at: null }] },
      [`${api}/api/v1/public/site/courses/python/?lang=ru`]: { title: 'Python', tagline: 'a', body: 'b' },
      [`${api}/api/v1/public/site/courses/python/?lang=ky`]: { title: 'Python', tagline: 'а', body: 'б' },
      [`${api}/api/v1/public/site/courses/python/?lang=en`]: { title: 'Python', tagline: 'a', body: 'b' },
    }
    const { entries } = await sitemapEntries(api, async (url) => records[url] ?? null)
    const xml = sitemapXml(SITE, entries)
    const locs = [...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1])
    expect(locs).toHaveLength(STATIC_PATHS.length * 3 + 2 + 1)
    expect(locs).toContain('https://www.okurmenkids.com/ky/courses/python')
    expect(locs).not.toContain('https://www.okurmenkids.com/en/courses/python')
    expect(locs).not.toContain('https://www.okurmenkids.com/ky/news/hello')
    expect(locs.every((loc) => loc.startsWith('https://www.okurmenkids.com/'))).toBe(true)
    expect(xml).toContain('<lastmod>2026-11-01</lastmod>')
    expect(xml).not.toMatch(/preview|enroll/)
  })
})

describe('Organization JSON-LD', () => {
  it('uses only the CMS data, cleaned', () => {
    const ld = organizationLd(SITE, 'ru', {
      contacts: { phone: '+996504677725', email: 'a@b.kg', instagram: 'https://instagram.com/okurmen_kids', telegram: null },
      branches: [{ address: '​Улица Орозбекова, 136', working_hours: 'Пн–Вс, 10:00–20:00', latitude: 42.88, longitude: 74.6, map_url: 'https://go.2gis.com/x' }],
      about: { story: 'OKURMEN Kids  — академия.\n\nВторой абзац.' },
    })
    expect(ld['@type']).toEqual(['Organization', 'EducationalOrganization'])
    expect(ld.name).toBe('OKURMEN Kids')
    expect(ld.description).toBe('IT-академия для детей и подростков в Кыргызстане.')
    expect(ld.url).toBe('https://www.okurmenkids.com')
    expect(ld.logo).toMatchObject({ url: 'https://www.okurmenkids.com/icon-512.png', width: 512, height: 512 })
    expect(ld.address).toEqual({ '@type': 'PostalAddress', streetAddress: 'Улица Орозбекова, 136', addressLocality: 'Бишкек', addressCountry: 'KG' })
    expect(ld.sameAs).toEqual(['https://instagram.com/okurmen_kids'])
    expect(ld.openingHours).toBe('Mo-Su 10:00-20:00')
    expect(ld).not.toHaveProperty('aggregateRating')
  })

  it('parses only opening hours it understands', () => {
    expect(openingHours('Пн–Пт, 9:00–18:00')).toBe('Mo-Fr 09:00-18:00')
    expect(openingHours('по записи')).toBeNull()
  })
})

describe('vercel.json', () => {
  it('rewrites every static page to its prerendered HTML file, and only those', async () => {
    const { readFileSync } = await import('node:fs')
    const config = JSON.parse(readFileSync('vercel.json', 'utf8')) as { rewrites: { source: string; destination: string }[]; trailingSlash: boolean }
    const pages = config.rewrites[0].source.match(/\(([^)]+)\)/)![1].split('|').map((p) => `/${p}`)
    expect(['/', ...pages].sort()).toEqual([...STATIC_PATHS].sort())
    expect(config.rewrites[1].source).toContain(config.rewrites[0].source.slice(1))
    expect(config.rewrites.at(-1)).toEqual({ source: '/(.*)', destination: '/index.html' })
    expect(config.trailingSlash).toBe(false)
  })
})

describe('favicons and logo for Google', () => {
  const png = (file: string) => {
    const buf = readFileSync(`public/${file}`)
    expect(buf.subarray(1, 4).toString(), file).toBe('PNG')
    return { width: buf.readUInt32BE(16), height: buf.readUInt32BE(20) }
  }

  it('ships every size as a real file in public/', () => {
    for (const [file, size] of [['favicon-48x48.png', 48], ['favicon-96x96.png', 96], ['apple-touch-icon.png', 180], ['icon-192.png', 192], ['icon-512.png', 512]] as const) {
      expect(png(file), file).toEqual({ width: size, height: size })
    }
    const ico = readFileSync('public/favicon.ico')
    expect(ico.readUInt16LE(2)).toBe(1) // ICO
    const sizes = Array.from({ length: ico.readUInt16LE(4) }, (_, i) => ico[6 + i * 16] || 256)
    expect(sizes.sort((a, b) => a - b)).toEqual([16, 32, 48])
  })

  it('has a transparent background — no white backing, brand colours fully opaque', async () => {
    const { PNG } = await import('./png')
    for (const file of ['favicon-48x48.png', 'favicon-96x96.png', 'apple-touch-icon.png', 'icon-192.png', 'icon-512.png']) {
      const img = PNG(readFileSync(`public/${file}`))
      expect(img.channels, file).toBe(4)
      const alphaAt = (x: number, y: number) => img.pixel(x, y)[3]
      const mid = Math.floor(img.width / 2)
      expect(alphaAt(0, 0), `${file} corner`).toBe(0)
      expect(alphaAt(img.width - 1, img.height - 1), `${file} corner`).toBe(0)
      expect(alphaAt(mid, Math.floor(img.height * 0.8)), `${file} inside the ring, below KIDS`).toBe(0)
      let white = 0
      let opaque = 0
      for (let y = 0; y < img.height; y++) for (let x = 0; x < img.width; x++) {
        const [r, g, b, a] = img.pixel(x, y)
        if (a > 0 && r > 240 && g > 240 && b > 240) white++
        if (a === 255) opaque++
      }
      expect(white, `${file} white pixels`).toBe(0)
      expect(opaque, `${file} opaque brand pixels`).toBeGreaterThan(0)
    }
    const ico = readFileSync('public/favicon.ico')
    for (let i = 0; i < ico.readUInt16LE(4); i++) {
      const offset = ico.readUInt32LE(6 + i * 16 + 12)
      const frame = PNG(ico.subarray(offset, offset + ico.readUInt32LE(6 + i * 16 + 8)))
      expect(frame.channels).toBe(4)
      expect(frame.pixel(0, 0)[3]).toBe(0)
    }
  })

  it('declares one consistent icon set in the HTML head and the manifest', () => {
    const html = readFileSync('index.html', 'utf8')
    const links = [...html.matchAll(/<link rel="(icon|apple-touch-icon|shortcut icon)"[^>]*>/g)].map((m) => m[0])
    expect(links).toEqual([
      '<link rel="icon" href="/favicon.ico" sizes="16x16 32x32 48x48" />',
      '<link rel="icon" type="image/png" sizes="48x48" href="/favicon-48x48.png" />',
      '<link rel="icon" type="image/png" sizes="96x96" href="/favicon-96x96.png" />',
      '<link rel="icon" type="image/png" sizes="192x192" href="/icon-192.png" />',
      '<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png" />',
    ])
    const manifest = JSON.parse(readFileSync('public/site.webmanifest', 'utf8'))
    expect(manifest.name).toBe('OKURMEN Kids')
    expect(manifest.icons.map((i: { src: string }) => i.src)).toEqual(['/icon-192.png', '/icon-512.png'])
  })

  it('points the Organization logo at a square image of at least 112×112', () => {
    expect(LOGO.path).toBe('/icon-512.png')
    const { width, height } = png(LOGO.path.slice(1))
    expect(width).toBe(LOGO.width)
    expect(height).toBe(LOGO.height)
    expect(Math.min(width, height)).toBeGreaterThanOrEqual(112)
  })

  it('spells the public brand «OKURMEN Kids» in the HTML template and public files, never «Digital»', () => {
    for (const file of ['index.html', 'public/site.webmanifest', 'public/robots.txt']) {
      const text = readFileSync(file, 'utf8')
      expect(text, file).not.toMatch(/digital/i)
      expect(text, file).not.toContain('OKURMEN KIDS')
    }
    expect(BRAND).toBe('OKURMEN Kids')
  })
})
