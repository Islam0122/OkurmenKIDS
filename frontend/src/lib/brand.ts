/**
 * OKURMENKIDS DIGITAL — the one source of the platform's name. «OKURMENKIDS»
 * is always one word; «DIGITAL» is the green part of the wordmark
 * (components/brand/BrandWordmark). The logo asset itself is not touched.
 */
export const BRAND = {
  /** In running text, titles and metadata. */
  name: 'OkurmenKids Digital',
  /** The wordmark, upper case: first part ink, second part green. */
  wordmark: { lead: 'OKURMENKIDS', accent: 'DIGITAL' },
  subtitle: 'ОБРАЗОВАТЕЛЬНАЯ ЭКОСИСТЕМА',
  description: 'OkurmenKids Digital — образовательная экосистема академии Okurmen Kids: LMS, тренировки и экзамены, расписание, рейтинг, новости и программы в одном месте.',
  copyright: '© 2026 OkurmenKids Digital. All rights reserved.',
  credit: 'Created by Islam Duishobaev.',
  developer: 'Islam Duishobaev',
} as const

/** `OkurmenKids Digital — <page>` (or the bare name). */
export function brandTitle(page?: string): string {
  return page ? `${BRAND.name} — ${page}` : BRAND.name
}
