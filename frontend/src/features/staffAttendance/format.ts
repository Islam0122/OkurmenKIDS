/** Время учёта посещаемости показывается в часовом поясе офиса (его отдаёт
 * backend), а не в поясе устройства — у сотрудника в поездке часы могут
 * стоять по другому поясу. */

export const DEFAULT_TZ = 'Asia/Bishkek'

function parts(date: Date, timeZone: string): Record<string, string> {
  const out: Record<string, string> = {}
  for (const p of new Intl.DateTimeFormat('en-GB', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(date)) {
    out[p.type] = p.value
  }
  return out
}

export function formatTime(iso: string | null | undefined, timeZone: string = DEFAULT_TZ): string {
  if (!iso) return '—'
  return new Intl.DateTimeFormat('ru-RU', { timeZone, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(new Date(iso))
}

export function formatDateTime(iso: string | null | undefined, timeZone: string = DEFAULT_TZ): string {
  if (!iso) return '—'
  return new Intl.DateTimeFormat('ru-RU', {
    timeZone,
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).format(new Date(iso))
}

/** `2026-10-21` → «ср, 21 окт. 2026». Календарная дата, без часового пояса. */
export function formatDay(day: string, withYear = true): string {
  const [y, m, d] = day.split('-').map(Number)
  return new Intl.DateTimeFormat('ru-RU', {
    timeZone: 'UTC',
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    ...(withYear ? { year: 'numeric' } : {}),
  }).format(new Date(Date.UTC(y, m - 1, d)))
}

export function formatLongDate(date: Date, timeZone: string = DEFAULT_TZ): string {
  const text = new Intl.DateTimeFormat('ru-RU', { timeZone, weekday: 'long', day: 'numeric', month: 'long' }).format(date)
  return text.charAt(0).toUpperCase() + text.slice(1)
}

export function formatClock(date: Date, timeZone: string = DEFAULT_TZ): string {
  return new Intl.DateTimeFormat('ru-RU', { timeZone, hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' }).format(date)
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '—'
  const total = Math.max(0, Math.floor(seconds / 60))
  const h = Math.floor(total / 60)
  const m = total % 60
  if (h === 0) return `${m} мин`
  return m === 0 ? `${h} ч` : `${h} ч ${m} мин`
}

export function formatLate(minutes: number): string {
  if (minutes <= 0) return '—'
  return minutes < 60 ? `${minutes} мин` : formatDuration(minutes * 60)
}

/** Значение для `<input type="datetime-local">` в поясе офиса. */
export function toZonedInput(iso: string | null | undefined, timeZone: string = DEFAULT_TZ): string {
  if (!iso) return ''
  const p = parts(new Date(iso), timeZone)
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`
}

/** Смещение пояса относительно UTC (мин) в момент `utcMs`. */
function offsetMinutes(utcMs: number, timeZone: string): number {
  const p = parts(new Date(utcMs), timeZone)
  const asUtc = Date.UTC(Number(p.year), Number(p.month) - 1, Number(p.day), Number(p.hour), Number(p.minute), Number(p.second))
  return Math.round((asUtc - utcMs) / 60000)
}

/** `2026-10-21T09:05` (время офиса) → ISO в UTC для API. */
export function fromZonedInput(value: string, timeZone: string = DEFAULT_TZ): string | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value)
  if (!match) return null
  const [, y, mo, d, h, mi] = match.map(Number)
  const guess = Date.UTC(y, mo - 1, d, h, mi)
  let utc = guess - offsetMinutes(guess, timeZone) * 60000
  utc = guess - offsetMinutes(utc, timeZone) * 60000 // уточнение на границе перехода на летнее время
  return new Date(utc).toISOString()
}

/** Сегодняшняя дата офиса `YYYY-MM-DD`. */
export function zonedToday(timeZone: string = DEFAULT_TZ, now: Date = new Date()): string {
  const p = parts(now, timeZone)
  return `${p.year}-${p.month}-${p.day}`
}

export function shiftDay(day: string, delta: number): string {
  const [y, m, d] = day.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d + delta)).toISOString().slice(0, 10)
}

export function shiftMonth(month: string, delta: number): string {
  const [y, m] = month.split('-').map(Number)
  const date = new Date(Date.UTC(y, m - 1 + delta, 1))
  return date.toISOString().slice(0, 7)
}

export function formatMonth(month: string): string {
  const [y, m] = month.split('-').map(Number)
  const label = new Intl.DateTimeFormat('ru-RU', { timeZone: 'UTC', month: 'long', year: 'numeric' }).format(new Date(Date.UTC(y, m - 1, 1)))
  return label.charAt(0).toUpperCase() + label.slice(1)
}

export function formatDistance(meters: number | null | undefined): string {
  if (meters === null || meters === undefined) return '—'
  return `${Math.round(meters)} м`
}
