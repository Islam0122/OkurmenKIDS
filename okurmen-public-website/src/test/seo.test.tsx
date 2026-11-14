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
  it('is «Okurmen Kids» everywhere public — no «Digital» in any page copy or UI string', () => {
    expect(BRAND).toBe('Okurmen Kids')
    expect(APP_BRAND.name).toBe('Okurmen Kids')
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
    expect(detailTitle('ru', 'courses', 'Премиум')).toBe('Премиум — курс для детей в Бишкеке | Okurmen Kids')
    expect(detailTitle('ru', 'news', '🚀 Ученики Okurmen Kids посетили Ololo!')).toBe('Ученики Okurmen Kids посетили Ololo! — новости | Okurmen Kids')
    const long = detailTitle('ru', 'news', 'Благодарственные письма родителям лучших учеников академии за отличную учёбу в октябре')
    expect(long.length).toBeLessThanOrEqual(70)
    expect(long.endsWith('— новости | Okurmen Kids')).toBe(true)
    expect(detailTitle('ky', 'courses', 'X', 'SEO заголовок')).toBe('SEO заголовок — Okurmen Kids')
  })

  it('gives an item with the same name a different title in every language', () => {
    for (const section of ['courses', 'events', 'achievements', 'team', 'news', 'projects'] as const) {
      for (const name of ['Okurmen Kids Club — NEXT', 'Нурсултан Караталов — IT-тренер', 'А'.repeat(90)]) {
        const titles = LANGS.map((lang) => detailTitle(lang, section, name))
        expect(new Set(titles).size, `${section} ${name.slice(0, 20)}`).toBe(3)
        for (const title of titles) expect(title.length).toBeLessThanOrEqual(70)
      }
    }
  })

  it('tells student projects with the same name apart by their own description and lists real technologies', () => {
    const a = { title: 'ShopVerce', short_description: 'Магазин электроники и техники', technologies: ['React HTML CSS JavaScript'] }
    const b = { title: 'ShopVerce', short_description: 'Магазин электроники и гаджетов', technologies: ['HTML CSS JS', 'React'] }
    expect(detailTitle('ru', 'projects', a.title, null, a.short_description)).toBe('ShopVerce — Магазин электроники и техники | Okurmen Kids')
    expect(detailTitle('ru', 'projects', b.title, null, b.short_description)).not.toBe(detailTitle('ru', 'projects', a.title, null, a.short_description))
    expect(projectText(b, 'ru')).toBe('Магазин электроники и гаджетов. Технологии: HTML, CSS, JS, React')
  })

  it('uses the item text for the description, padding a short one with a fact about the section', () => {
    expect(detailDescription('ru', 'projects', 'Интернет-магазин на React.')).toBe('Интернет-магазин на React. Проект ученика IT-академии Okurmen Kids в Бишкеке.')
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
    expect(all).toContain('<meta property="og:site_name" content="Okurmen Kids" />')
    expect(all).toContain('index, follow')
  })

  it('sets the same tags in the browser (Seo component)', () => {
    const renderAt = (url: string, lang: Lang, langs?: Lang[] | null) => render(
      <MemoryRouter initialEntries={[url]}>
        <I18nProvider lang={lang}><Seo title="Новость | Okurmen Kids" description="Описание" langs={langs} /></I18nProvider>
      </MemoryRouter>,
    )
    renderAt('/ky/news/x/', 'ky', ['ru'])
    expect(document.title).toBe('Новость | Okurmen Kids')
    expect(document.documentElement.lang).toBe('ky')
    expect(document.head.querySelector('link[rel="canonical"]')?.getAttribute('href')).toBe('https://kids.test/news/x')
    expect(document.head.querySelectorAll('link[hreflang]')).toHaveLength(0)
    expect(document.head.querySelector('meta[property="og:site_name"]')?.getAttribute('content')).toBe('Okurmen Kids')

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

describe('Brand search: Latin and Cyrillic', () => {
  it('homepage title and description carry the brand, the description also in Cyrillic', () => {
    expect(PAGES.ru['/'].title).toBe('Okurmen Kids — Академия программирования для детей в Бишкеке')
    expect(PAGES.ru['/'].description).toBe('Окурмен Кидс (Okurmen Kids) — образовательная академия для детей в Бишкеке. Программирование, IT-курсы, Python, веб-разработка и современные технологии.')
    expect(PAGES.ky['/'].description).toMatch(/^Окурмен Кидс \(Okurmen Kids\)/)
  })

  it('WebSite JSON-LD names the brand and its search spellings', () => {
    const ld = websiteLd(SITE, 'ru')
    expect(ld.name).toBe('Okurmen Kids')
    expect(ld.alternateName).toEqual(['Окурмен Кидс', 'ОкурменKids', 'Окурмен Кидс Бишкек', 'okurmenkids'])
    expect(ld.url).toBe('https://www.okurmenkids.com/')
  })

  it('visible homepage text mentions «Окурмен Кидс» once, naturally, in RU and KG — not in EN', () => {
    for (const dict of [ru, ky]) {
      expect(dict['home.hero.lead']).toMatch(/^Okurmen Kids \(Окурмен Кидс\) — /)
      expect(dict['footer.about']).toMatch(/^Okurmen Kids \(Окурмен Кидс\) — /)
      // No keyword stuffing: one Cyrillic mention per string.
      for (const key of ['home.hero.lead', 'footer.about'] as const) expect(dict[key].split('Окурмен Кидс')).toHaveLength(2)
    }
    expect(en['home.hero.lead']).not.toContain('Окурмен')
  })
})

describe('Organization JSON-LD', () => {
  it('uses only the CMS data, cleaned', () => {
    const ld = organizationLd(SITE, 'ru', {
      contacts: { phone: '+996504677725', email: 'a@b.kg', instagram: 'https://instagram.com/okurmen_kids', telegram: null },
      branches: [{ address: '​Улица Орозбекова, 136', working_hours: 'Пн–Вс, 10:00–20:00', latitude: 42.88, longitude: 74.6, map_url: 'https://go.2gis.com/x' }],
      about: { story: 'Okurmen Kids  — академия.\n\nВторой абзац.' },
    })
    expect(ld['@type']).toEqual(['Organization', 'EducationalOrganization'])
    expect(ld.name).toBe('Okurmen Kids')
    expect(ld.alternateName).toBe('Окурмен Кидс')
    expect(ld.description).toBe('Окурмен Кидс (Okurmen Kids) — академия программирования для детей и подростков в Бишкеке.')
    expect(ld.url).toBe('https://www.okurmenkids.com/')
    expect(ld.telephone).toBe('+996504677725')
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

  it('is the original round logo on a transparent square: only the corners outside the ring are cut', async () => {
    const { PNG } = await import('./png')
    for (const file of ['favicon-48x48.png', 'favicon-96x96.png', 'icon-192.png', 'icon-512.png']) {
      const img = PNG(readFileSync(`public/${file}`))
      const n = img.width - 1
      const mid = Math.floor(img.width / 2)
      expect(img.channels, `${file} alpha channel`).toBe(4)
      for (const [x, y] of [[0, 0], [n, 0], [0, n], [n, n]]) expect(img.pixel(x, y)[3], `${file} corner ${x},${y}`).toBe(0)
      // The logo's own white circle stays: opaque white between «KIDS» and the bottom of the ring.
      expect(img.pixel(mid, Math.floor(img.height * 0.8)), `${file} white circle`).toEqual([255, 255, 255, 255])
      // Nothing is cut: the outermost pixel rows and columns are (practically) empty.
      let edge = 0
      for (let i = 0; i <= n; i++) edge = Math.max(edge, img.pixel(i, 0)[3], img.pixel(i, n)[3], img.pixel(0, i)[3], img.pixel(n, i)[3])
      expect(edge, `${file} edge alpha`).toBeLessThanOrEqual(4)
    }
    const ico = readFileSync('public/favicon.ico')
    for (let i = 0; i < ico.readUInt16LE(4); i++) {
      const offset = ico.readUInt32LE(6 + i * 16 + 12)
      const frame = PNG(ico.subarray(offset, offset + ico.readUInt32LE(6 + i * 16 + 8)))
      expect(frame.channels, `ico frame ${frame.width}`).toBe(4)
      expect(frame.pixel(0, 0)[3], `ico frame ${frame.width} corner`).toBe(0)
      expect(frame.pixel(frame.width >> 1, Math.floor(frame.height * 0.8))[3], `ico frame ${frame.width} white circle`).toBe(255)
    }
    // iOS paints transparency black, so the home-screen icon stays opaque.
    expect(PNG(readFileSync('public/apple-touch-icon.png')).channels).toBe(3)
  })

  it('declares one consistent icon set in the HTML head and the manifest', () => {
    const html = readFileSync('index.html', 'utf8')
    const links = [...html.matchAll(/<link rel="(icon|apple-touch-icon|shortcut icon)"[^>]*>/g)].map((m) => m[0])
    expect(links).toEqual([
      '<link rel="icon" href="/favicon.ico?v=4" sizes="16x16 32x32 48x48" />',
      '<link rel="icon" type="image/png" sizes="48x48" href="/favicon-48x48.png?v=4" />',
      '<link rel="icon" type="image/png" sizes="96x96" href="/favicon-96x96.png?v=4" />',
      '<link rel="icon" type="image/png" sizes="192x192" href="/icon-192.png?v=4" />',
      '<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png?v=4" />',
    ])
    const manifest = JSON.parse(readFileSync('public/site.webmanifest', 'utf8'))
    expect(manifest.name).toBe('OKURMEN Kids') // installed-app label: visual brand, unchanged
    expect(manifest.icons.map((i: { src: string }) => i.src)).toEqual(['/icon-192.png', '/icon-512.png'])
  })

  it('points the Organization logo at a square image of at least 112×112', () => {
    expect(LOGO.path).toBe('/icon-512.png')
    const { width, height } = png(LOGO.path.slice(1))
    expect(width).toBe(LOGO.width)
    expect(height).toBe(LOGO.height)
    expect(Math.min(width, height)).toBeGreaterThanOrEqual(112)
  })

  it('spells the public brand «Okurmen Kids» in the HTML template and public files, never «Digital»', () => {
    for (const file of ['index.html', 'public/site.webmanifest', 'public/robots.txt']) {
      const text = readFileSync(file, 'utf8')
      expect(text, file).not.toMatch(/digital/i)
      expect(text, file).not.toContain('OKURMEN KIDS')
    }
    expect(BRAND).toBe('Okurmen Kids')
  })
})
