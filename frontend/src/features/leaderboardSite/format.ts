import type { LeaderboardPeriod } from '@/types/leaderboard'

/** The academy's calendar — period bounds come from the server in this zone. */
export const TIME_ZONE = 'Asia/Bishkek'

export const MONTHS = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']
const MONTHS_GENITIVE = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']

const numberFormat = new Intl.NumberFormat('ru-RU')

export const formatNumber = (value: number) => numberFormat.format(value)

/** A calendar date string (YYYY-MM-DD) as its parts — never through `Date`,
 * so the browser's own time zone can't shift the day. */
export function parseDay(value: string): { year: number; month: number; day: number } {
  const [year, month, day] = value.split('-').map(Number)
  return { year, month, day }
}

export function addDays(value: string, days: number): string {
  const { year, month, day } = parseDay(value)
  const date = new Date(Date.UTC(year, month - 1, day + days))
  return date.toISOString().slice(0, 10)
}

export function formatDay(value: string, withYear = true): string {
  const { year, month, day } = parseDay(value)
  return `${day} ${MONTHS_GENITIVE[month - 1]}${withYear ? ` ${year}` : ''}`
}

export function weekRangeLabel(start: string): string {
  const end = addDays(start, 6)
  const a = parseDay(start)
  const b = parseDay(end)
  if (a.year !== b.year) return `${formatDay(start)} — ${formatDay(end)}`
  if (a.month !== b.month) return `${formatDay(start, false)} — ${formatDay(end)}`
  return `${a.day}–${b.day} ${MONTHS_GENITIVE[b.month - 1]} ${b.year}`
}

export function periodTitle(period: LeaderboardPeriod): string {
  const { year, month } = parseDay(period.start)
  if (period.type === 'year') return `${year} год`
  if (period.type === 'month') return `${MONTHS[month - 1]} ${year}`
  return `Неделя ${weekRangeLabel(period.start)}`
}

export function periodRange(period: LeaderboardPeriod): string {
  return `${formatDay(period.start)} — ${formatDay(period.end)}`
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  return new Date(value).toLocaleString('ru-RU', {
    timeZone: TIME_ZONE, day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

/** Russian plural: plural(5, ['студент', 'студента', 'студентов']). */
export function plural(n: number, forms: [string, string, string]): string {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return forms[0]
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return forms[1]
  return forms[2]
}
