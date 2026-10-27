import { useEffect } from 'react'

export interface DocumentMeta {
  title: string
  description?: string
  /** Канонический адрес страницы (абсолютный). */
  url?: string
  /** Структурированные данные (schema.org JSON-LD), например JobPosting. */
  jsonLd?: Record<string, unknown> | null
  /** Не индексировать (закрытая вакансия, служебная страница). */
  noindex?: boolean
}

function setMeta(attr: 'name' | 'property', key: string, value: string | undefined): () => void {
  let el = document.head.querySelector<HTMLMetaElement>(`meta[${attr}="${key}"]`)
  const created = !el
  const previous = el?.content
  if (value === undefined) return () => undefined
  if (!el) {
    el = document.createElement('meta')
    el.setAttribute(attr, key)
    document.head.appendChild(el)
  }
  el.content = value
  return () => {
    if (created) el?.remove()
    else if (el && previous !== undefined) el.content = previous
  }
}

/** SEO-метаданные страницы SPA: title, description, Open Graph, canonical и
 * JSON-LD. Всё восстанавливается при уходе со страницы. */
export function useDocumentMeta({ title, description, url, jsonLd, noindex }: DocumentMeta) {
  const ld = jsonLd ? JSON.stringify(jsonLd) : ''
  useEffect(() => {
    const previousTitle = document.title
    document.title = title
    const restore = [
      setMeta('name', 'description', description),
      setMeta('property', 'og:title', title),
      setMeta('property', 'og:description', description),
      setMeta('property', 'og:type', 'website'),
      setMeta('property', 'og:url', url),
      setMeta('name', 'robots', noindex ? 'noindex' : undefined),
    ]
    let canonical: HTMLLinkElement | null = null
    if (url) {
      canonical = document.createElement('link')
      canonical.rel = 'canonical'
      canonical.href = url
      document.head.appendChild(canonical)
    }
    let script: HTMLScriptElement | null = null
    if (ld) {
      script = document.createElement('script')
      script.type = 'application/ld+json'
      script.text = ld
      document.head.appendChild(script)
    }
    return () => {
      document.title = previousTitle
      restore.forEach((fn) => fn())
      canonical?.remove()
      script?.remove()
    }
  }, [title, description, url, ld, noindex])
}

export function absoluteUrl(path: string): string {
  return `${window.location.origin}${path}`
}
