import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

import { BRAND } from '@/app/config/site'
import { LANGS, localizedPath, splitLangPath, useI18n } from '@/i18n'
import { absoluteUrl, mediaUrl } from '@/utils/media'

interface Props {
  title?: string
  description?: string
  image?: string | null
  type?: 'website' | 'article' | 'event'
  /** schema.org JSON-LD objects for this page. */
  jsonLd?: Record<string, unknown> | Record<string, unknown>[]
  noindex?: boolean
  publishedAt?: string
}

const OG_LOCALE = { ru: 'ru_RU', ky: 'ky_KG', en: 'en_US' } as const

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
 * Title, description, canonical, hreflang alternates, Open Graph / Twitter
 * and JSON-LD for the current page. (Crawlers that do not run JavaScript get
 * the same tags from the Vercel middleware — see middleware.ts.)
 */
export function Seo({ title, description, image, type = 'website', jsonLd, noindex, publishedAt }: Props) {
  const { t, lang } = useI18n()
  const { pathname } = useLocation()
  const fullTitle = title ? `${title} — ${BRAND.short}` : t('meta.title')
  const desc = (description || t('meta.description')).slice(0, 300)
  const { rest } = splitLangPath(pathname)
  const canonical = absoluteUrl(localizedPath(lang, rest))
  const ogImage = image ? absoluteUrl(mediaUrl(image) ?? image) : absoluteUrl('/og-image.png')
  const ld = JSON.stringify(jsonLd ?? null)

  useEffect(() => {
    document.title = fullTitle
    meta('name', 'description', desc)
    meta('name', 'robots', noindex ? 'noindex, nofollow' : 'index, follow, max-image-preview:large')
    meta('property', 'og:title', fullTitle)
    meta('property', 'og:description', desc)
    meta('property', 'og:type', type === 'event' ? 'website' : type)
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
    for (const code of [...LANGS, 'x-default'] as const) {
      const link = document.createElement('link')
      link.rel = 'alternate'
      link.hreflang = code
      link.href = absoluteUrl(localizedPath(code === 'x-default' ? 'ru' : code, rest))
      document.head.appendChild(link)
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
  }, [fullTitle, desc, noindex, type, canonical, ogImage, lang, rest, ld, publishedAt])

  return null
}

/** schema.org Organization — the academy (used on the homepage, about and contacts). */
export function organizationLd(options: { phone?: string | null; email?: string | null; sameAs?: (string | null)[]; addresses?: string[] } = {}) {
  return {
    '@context': 'https://schema.org',
    '@type': 'EducationalOrganization',
    name: BRAND.name,
    alternateName: 'Okurmen Kids',
    url: absoluteUrl('/'),
    logo: absoluteUrl('/logo.png'),
    slogan: BRAND.tagline,
    ...(options.phone ? { telephone: options.phone } : {}),
    ...(options.email ? { email: options.email } : {}),
    ...(options.sameAs?.filter(Boolean).length ? { sameAs: options.sameAs.filter(Boolean) } : {}),
    ...(options.addresses?.length
      ? { address: options.addresses.map((a) => ({ '@type': 'PostalAddress', streetAddress: a, addressCountry: 'KG' })) }
      : { address: { '@type': 'PostalAddress', addressCountry: 'KG' } }),
  }
}

export function breadcrumbLd(items: { name: string; path: string }[]) {
  return {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: items.map((item, index) => ({ '@type': 'ListItem', position: index + 1, name: item.name, item: absoluteUrl(item.path) })),
  }
}
