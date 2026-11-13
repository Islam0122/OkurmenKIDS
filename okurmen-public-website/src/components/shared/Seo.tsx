import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

import { env } from '@/app/config/env'
import { useI18n } from '@/i18n'
import {
  breadcrumbLd,
  canonicalPath,
  detailDescription,
  detailTitle,
  HTML_LANG,
  LANGS,
  localized,
  OG_LOCALE,
  organizationLd,
  pageSeo,
  sectionCrumbs,
  splitLang,
  websiteLd,
  type JsonLd,
  type Lang,
  type OrgSettings,
  type Section,
  BRAND,
} from '@/seo/core'
import { absoluteUrl, mediaUrl } from '@/utils/media'

interface Props {
  /** A static page ('/', '/courses', …): its unique title and description come from src/seo/core.js. */
  page?: string
  /** Detail pages: the full title (see detailTitle) and description (see detailDescription). */
  title?: string
  description?: string
  image?: string | null
  type?: 'website' | 'article' | 'event'
  /** schema.org JSON-LD objects for this page. */
  jsonLd?: JsonLd | JsonLd[]
  noindex?: boolean
  publishedAt?: string
  /**
   * Languages this page really exists in (default: all three). A page shown
   * in a language it has no translation for points its canonical to the
   * original, and only real translations are listed as hreflang alternates.
   * `null` = still being determined (no alternates yet).
   */
  langs?: Lang[] | null
}

function upsert(selector: string, create: () => HTMLElement, apply: (el: HTMLElement) => void) {
  let el = document.head.querySelector<HTMLElement>(selector)
  if (!el) {
    el = create()
    document.head.appendChild(el)
  }
  apply(el)
}

function meta(attr: 'name' | 'property', key: string, content: string | undefined) {
  const selector = `meta[${attr}="${key}"]`
  if (!content) {
    document.head.querySelector(selector)?.remove()
    return
  }
  upsert(selector, () => {
    const el = document.createElement('meta')
    el.setAttribute(attr, key)
    return el
  }, (el) => el.setAttribute('content', content))
}

/**
 * Title, description, robots, canonical, hreflang alternates, Open Graph /
 * Twitter and JSON-LD for the current page. The same tags are in the built
 * HTML of every static page (scripts/prerender-seo.mjs) and, for crawlers,
 * of every detail page (middleware.ts) — all three use src/seo/core.js.
 */
export function Seo({ page, title, description, image, type = 'website', jsonLd, noindex, publishedAt, langs = LANGS }: Props) {
  const { lang } = useI18n()
  const { pathname } = useLocation()
  const staticSeo = page ? pageSeo(lang, page) : null
  const fullTitle = staticSeo?.title ?? title ?? pageSeo(lang, '/').title
  const desc = (staticSeo?.description ?? description ?? pageSeo(lang, '/').description).slice(0, 300)
  const rest = canonicalPath(splitLang(pathname).rest)
  const available = langs ?? [lang]
  const ownLang = available.includes(lang) ? lang : available[0]
  const canonical = absoluteUrl(localized(ownLang, rest))
  const alternates = !noindex && langs && langs.length > 1 && langs.includes(lang) ? langs : []
  const ogImage = image ? absoluteUrl(mediaUrl(image) ?? image) : absoluteUrl('/og-image.png')
  const ld = JSON.stringify(jsonLd ?? null)
  const altKey = alternates.join(',')

  useEffect(() => {
    document.title = fullTitle
    document.documentElement.lang = HTML_LANG[lang]
    meta('name', 'description', desc)
    meta('name', 'robots', noindex ? 'noindex, follow' : 'index, follow, max-image-preview:large')
    meta('property', 'og:site_name', BRAND)
    meta('property', 'og:title', fullTitle)
    meta('property', 'og:description', desc)
    meta('property', 'og:type', type === 'article' ? 'article' : 'website')
    meta('property', 'og:url', canonical)
    meta('property', 'og:image', ogImage)
    meta('property', 'og:locale', OG_LOCALE[lang])
    meta('property', 'article:published_time', publishedAt)
    meta('name', 'twitter:card', 'summary_large_image')
    meta('name', 'twitter:title', fullTitle)
    meta('name', 'twitter:description', desc)
    meta('name', 'twitter:image', ogImage)

    upsert('link[rel="canonical"]', () => Object.assign(document.createElement('link'), { rel: 'canonical' }), (el) => el.setAttribute('href', canonical))
    document.head.querySelectorAll('link[rel="alternate"][hreflang]').forEach((el) => el.remove())
    const codes = altKey ? (altKey.split(',') as Lang[]) : []
    if (codes.length) {
      for (const code of [...codes, 'x-default'] as const) {
        const link = document.createElement('link')
        link.rel = 'alternate'
        link.hreflang = code
        link.href = absoluteUrl(localized(code === 'x-default' ? (codes.includes('ru') ? 'ru' : codes[0]) : code, rest))
        document.head.appendChild(link)
      }
    }

    document.head.querySelectorAll('script[data-seo-jsonld]').forEach((el) => el.remove())
    const parsed = JSON.parse(ld) as Props['jsonLd'] | null
    if (parsed) {
      const script = document.createElement('script')
      script.type = 'application/ld+json'
      script.dataset.seoJsonld = 'true'
      script.textContent = JSON.stringify(parsed)
      document.head.appendChild(script)
    }
  }, [fullTitle, desc, noindex, type, canonical, ogImage, lang, rest, ld, publishedAt, altKey])

  return null
}

/* JSON-LD helpers bound to this site's canonical origin. */

export const orgLd = (lang: Lang, settings?: OrgSettings | null) => organizationLd(env.siteUrl, lang, settings)
export const siteLd = (lang: Lang) => websiteLd(env.siteUrl, lang)
/** Home › Section (› Item), localized. `section` is the first path segment: 'courses', 'about', … */
export const crumbsLd = (lang: Lang, section: string, item?: { name: string; slug: string }) =>
  breadcrumbLd(env.siteUrl, sectionCrumbs(lang, section as Section, item))
export { detailDescription, detailTitle }
