import { format, parseISO } from 'date-fns'
import { ru } from 'date-fns/locale'

/** Backend times are `HH:MM:SS` — trims to `HH:MM` for display. */
export function formatTime(value: string): string {
  return value.slice(0, 5)
}

export function formatTimeRange(start: string, end: string): string {
  return `${formatTime(start)}–${formatTime(end)}`
}

/** `2026-09-14` → `14 сентября 2026` (or without the year when `withYear` is false). */
export function formatDate(value: string, withYear = true): string {
  const date = parseISO(value)
  return format(date, withYear ? 'd MMMM yyyy' : 'd MMMM', { locale: ru })
}

export function formatDateShort(value: string): string {
  const date = parseISO(value)
  return format(date, 'dd.MM.yyyy')
}

export function formatWeekday(value: string): string {
  const date = parseISO(value)
  return format(date, 'EEEE', { locale: ru })
}

export function formatPercent(value: number): string {
  return `${Number.isInteger(value) ? value : value.toFixed(1)}%`
}

export function pluralize(count: number, one: string, few: string, many: string): string {
  const mod10 = count % 10
  const mod100 = count % 100
  if (mod10 === 1 && mod100 !== 11) return one
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few
  return many
}
