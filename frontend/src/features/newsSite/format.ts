import type { Lang } from '@/features/portal/i18n'

const LOCALE: Record<Lang, string> = { ru: 'ru-RU', kg: 'ky-KG', en: 'en-GB' }

/** «8 ноября 2026 г.» — the publication day in the academy's time zone. */
export function formatNewsDate(iso: string, lang: Lang): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return new Intl.DateTimeFormat(LOCALE[lang], { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'Asia/Bishkek' }).format(date)
}
