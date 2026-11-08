import type { Lang } from '@/features/portal/i18n'

const LOCALE: Record<Lang, string> = { ru: 'ru-RU', kg: 'ky-KG', en: 'en-GB' }

/** «2 ноября 2026 г.» / «2 November 2026» — a date-only ISO string, no time-zone shift. */
export function formatProjectDate(iso: string, lang: Lang): string {
  const [year, month, day] = iso.split('-').map(Number)
  if (!year || !month || !day) return iso
  return new Intl.DateTimeFormat(LOCALE[lang], { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' }).format(
    new Date(Date.UTC(year, month - 1, day)),
  )
}
