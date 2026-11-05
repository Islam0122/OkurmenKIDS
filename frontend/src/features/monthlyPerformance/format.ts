/** Форматирование «Общей статистики»: русская запятая, «—» для отсутствующих данных. */

const MONTHS_GENITIVE = [
  'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
  'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
]

export const MONTHS = [
  'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
]

function decimal(value: number): string {
  const rounded = Math.round(value * 10) / 10
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1).replace('.', ',')
}

export function formatPct(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : `${decimal(value)}%`
}

export function formatCount(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : value.toLocaleString('ru-RU')
}

/** Изменение за день: «+5», «−2,5». Для процентов — в процентных пунктах. */
export function formatChange(value: number, percent: boolean): string {
  const sign = value > 0 ? '+' : value < 0 ? '−' : ''
  return `${sign}${decimal(Math.abs(value))}${percent ? ' п.п.' : ''}`
}

/** `2026-11-03` → `3 ноября`. */
export function dayMonthLabel(iso: string): string {
  const [, month, day] = iso.split('-').map(Number)
  return `${day} ${MONTHS_GENITIVE[month - 1]}`
}

/** Дата и время в часовом поясе проекта: «5 ноября 2026, 14:05». */
export function formatDateTime(date: Date, timeZone: string, withSeconds = false): { date: string; time: string } {
  const parts = new Intl.DateTimeFormat('ru-RU', {
    timeZone, day: 'numeric', month: 'long', year: 'numeric', weekday: 'long',
  }).format(date)
  const time = new Intl.DateTimeFormat('ru-RU', {
    timeZone, hour: '2-digit', minute: '2-digit', ...(withSeconds ? { second: '2-digit' } : {}),
  }).format(date)
  return { date: parts.charAt(0).toUpperCase() + parts.slice(1), time }
}
