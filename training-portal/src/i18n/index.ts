import { ky, type Dictionary } from './ky'

/*
 * Kyrgyz is the main (and for now only) language. Russian and English
 * dictionaries plug in here with the same shape (Dictionary) when ready.
 */
export type Locale = 'ky' | 'ru' | 'en'

const dictionaries: Partial<Record<Locale, Dictionary>> = { ky }

export const locale: Locale = 'ky'

export const t: Dictionary = dictionaries[locale] ?? ky
