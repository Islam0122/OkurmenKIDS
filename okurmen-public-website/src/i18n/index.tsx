/**
 * Internationalisation: Russian (default, no URL prefix), Kyrgyz (/ky/...)
 * and English (/en/...). The language lives in the URL so every page has an
 * indexable address per language (hreflang in <Seo>). UI strings come from
 * the dictionaries in ./locales; content strings come translated from the
 * API (?lang=…, Russian fallback on the server).
 */
import { createContext, useContext, useEffect, useMemo, type ReactNode } from 'react'

import { setApiLanguage } from '@/services/api/client'
import { formatDateIn } from './dates'
import type { Lang } from '@/types/api'

import { en } from './locales/en'
import { ky } from './locales/ky'
import { ru, type MessageKey, type Messages } from './locales/ru'

export type { MessageKey }

export const LANGS: Lang[] = ['ru', 'ky', 'en']
export const DEFAULT_LANG: Lang = 'ru'
export const LANG_LABEL: Record<Lang, string> = { ru: 'Русский', ky: 'Кыргызча', en: 'English' }
export const LANG_SHORT: Record<Lang, string> = { ru: 'RU', ky: 'KG', en: 'EN' }
const HTML_LANG: Record<Lang, string> = { ru: 'ru', ky: 'ky', en: 'en' }
const LOCALE: Record<Lang, string> = { ru: 'ru-RU', ky: 'ky-KG', en: 'en-GB' }
const DICTIONARIES: Record<Lang, Messages> = { ru, ky, en }

export type Translate = (key: MessageKey, vars?: Record<string, string | number>) => string

export interface I18n {
  lang: Lang
  t: Translate
  /** '/courses' → '/ky/courses' in Kyrgyz. */
  path: (to: string) => string
  locale: string
  formatDate: (iso: string, options?: Intl.DateTimeFormatOptions) => string
}

export function translate(lang: Lang): Translate {
  const dict = DICTIONARIES[lang]
  return (key, vars) => {
    let text: string = dict[key] ?? ru[key] ?? key
    if (vars) for (const [name, value] of Object.entries(vars)) text = text.replaceAll(`{${name}}`, String(value))
    return text
  }
}

export function localizedPath(lang: Lang, to: string): string {
  if (/^(https?:|mailto:|tel:|#)/.test(to)) return to
  const clean = to.startsWith('/') ? to : `/${to}`
  if (lang === DEFAULT_LANG) return clean
  return clean === '/' ? `/${lang}` : `/${lang}${clean}`
}

/** '/ky/courses/python' → { lang: 'ky', rest: '/courses/python' } */
export function splitLangPath(pathname: string): { lang: Lang; rest: string } {
  const match = pathname.match(/^\/(ky|en)(\/.*)?$/)
  if (match) return { lang: match[1] as Lang, rest: match[2] || '/' }
  return { lang: DEFAULT_LANG, rest: pathname || '/' }
}

const I18nContext = createContext<I18n | null>(null)

export function I18nProvider({ lang, children }: { lang: Lang; children: ReactNode }) {
  const value = useMemo<I18n>(() => {
    const locale = LOCALE[lang]
    return {
      lang,
      t: translate(lang),
      path: (to) => localizedPath(lang, to),
      locale,
      formatDate: (iso, options = { day: 'numeric', month: 'long', year: 'numeric' }) => formatDateIn(lang, locale, iso, options),
    }
  }, [lang])

  // Before children render, so the very first request already carries the language.
  setApiLanguage(lang)
  useEffect(() => {
    document.documentElement.lang = HTML_LANG[lang]
    try {
      localStorage.setItem('okurmen_lang', lang)
    } catch {
      /* private mode */
    }
  }, [lang])

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useI18n(): I18n {
  const value = useContext(I18nContext)
  if (!value) throw new Error('useI18n must be used inside <I18nProvider>')
  return value
}
