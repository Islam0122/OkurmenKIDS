/** Types for core.js (plain JS so build scripts and Vercel functions can import it too). */
export type Lang = 'ru' | 'ky' | 'en'
export type Section = 'courses' | 'events' | 'achievements' | 'team' | 'news' | 'projects'
export type JsonLd = Record<string, unknown>

export const SITE_ORIGIN: string
export const BRAND: string
export const BRAND_ALT: string[]
export const LOGO: { path: string; width: number; height: number }
export const LANGS: Lang[]
export const DEFAULT_LANG: Lang
export const HTML_LANG: Record<Lang, string>
export const OG_LOCALE: Record<Lang, string>
export const STATIC_PATHS: string[]

export interface PageSeo {
  name: string
  title: string
  description: string
}
export const PAGES: Record<Lang, Record<string, PageSeo>>
export function pageSeo(lang: Lang, path: string): PageSeo

export interface DetailSpec {
  api: (slug: string) => string
  fields: string[] | null
  name: (data: any) => string
  subtitle?: (data: any) => string | null | undefined
  text: (data: any, lang?: Lang) => string
  image: (data: any) => string | null | undefined
}
export const DETAIL: Record<Section, DetailSpec>

export function localized(lang: Lang, path: string): string
export function splitLang(pathname: string): { lang: Lang; rest: string }
export function canonicalPath(path: string): string
export function absolute(site: string, path: string): string
export function plainText(value: unknown): string
export function withBrand(title: string): string
export function detailTitle(lang: Lang, section: Section, name: string, seoTitle?: string | null, subtitle?: string | null): string
export function projectText(project: { short_description?: string | null; description?: string | null; technologies?: string[] }, lang?: Lang): string
export function detailDescription(lang: Lang, section: Section, text: string | null | undefined, seoDescription?: string | null): string
export function translatedLangs(section: Section, versions: Partial<Record<Lang, Record<string, unknown> | null | undefined>>): Lang[]
export function openingHours(text: string | null | undefined): string | null

export interface OrgSettings {
  contacts?: Partial<Record<'phone' | 'email' | 'instagram' | 'facebook' | 'youtube' | 'tiktok' | 'telegram', string | null>>
  branches?: { address?: string | null; working_hours?: string | null; latitude?: number | null; longitude?: number | null; map_url?: string | null }[]
  about?: { story?: string | null }
}
export function organizationLd(site: string, lang: Lang, settings?: OrgSettings | null): JsonLd
export function websiteLd(site: string, lang: Lang): JsonLd
export function breadcrumbLd(site: string, items: { name: string; path: string }[]): JsonLd
export function sectionCrumbs(lang: Lang, section: Section | string, item?: { name: string; slug: string }): { name: string; path: string }[]
export function provider(site: string): JsonLd

export interface HeadMeta {
  site: string
  lang: Lang
  /** Unprefixed path, e.g. '/courses/python'. */
  path: string
  title: string
  description: string
  image?: string | null
  type?: 'website' | 'article' | 'event'
  /** Languages this page really exists in (default: all). */
  langs?: Lang[]
  noindex?: boolean
  jsonLd?: JsonLd | JsonLd[] | null
  publishedAt?: string | null
}
export const SEO_START: string
export const SEO_END: string
export function headTags(meta: HeadMeta): string
export function renderPage(template: string, meta: HeadMeta, body?: string | null): string
export function noscriptBody(lang: Lang, heading: string, description: string): string

export interface SitemapEntry {
  path: string
  langs: Lang[]
  lastmod: string | null
  priority: string
  changefreq: string
}
export function sitemapEntries(api: string, fetchJson: (url: string) => Promise<any>): Promise<{ entries: SitemapEntry[]; content: number }>
export function sitemapXml(site: string, entries: SitemapEntry[]): string
