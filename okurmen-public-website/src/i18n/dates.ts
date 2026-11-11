/**
 * Date formatting. Kyrgyz locale data is missing from some browsers (Intl
 * then silently falls back to English: «November 14 at 06:29 AM»). For ky
 * without native support we build the same output as ICU's ky locale
 * («2026-ж., 14-ноябрь», «14-ноябрь, ишемби», «14-ноябрь 06:29»).
 */
const KY_MONTHS = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь', 'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь']
const KY_MONTHS_SHORT = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']
const KY_WEEKDAYS = ['жекшемби', 'дүйшөмбү', 'шейшемби', 'шаршемби', 'бейшемби', 'жума', 'ишемби']

let kyNative: boolean | null = null
export function hasNativeKyrgyz(): boolean {
  if (kyNative === null) {
    try {
      kyNative = Intl.DateTimeFormat.supportedLocalesOf(['ky']).length > 0
    } catch {
      kyNative = false
    }
  }
  return kyNative
}

const pad = (n: number) => String(n).padStart(2, '0')

export function formatKyrgyz(date: Date, o: Intl.DateTimeFormatOptions): string {
  const month = date.getMonth()
  const time = o.hour || o.minute ? `${pad(date.getHours())}:${pad(date.getMinutes())}` : ''
  if (o.month && !o.day) {
    const m = o.month === 'long' ? KY_MONTHS[month] : KY_MONTHS_SHORT[month]
    if (!o.year) return m.charAt(0).toUpperCase() + m.slice(1)
    return `${date.getFullYear()}-ж. ${m}${o.month === 'long' ? '' : '.'}`
  }
  let text = ''
  if (o.day) text = o.month === 'short' ? `${date.getDate()}-${KY_MONTHS_SHORT[month]}.` : `${date.getDate()}-${KY_MONTHS[month]}`
  if (o.weekday) text = text ? `${text}, ${KY_WEEKDAYS[date.getDay()]}` : KY_WEEKDAYS[date.getDay()]
  if (o.year) text = `${date.getFullYear()}-ж.${o.month === 'short' ? ' ' : ', '}${text}`
  return [text, time].filter(Boolean).join(' ')
}

export function formatDateIn(lang: string, locale: string, iso: string, options: Intl.DateTimeFormatOptions): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  if (lang === 'ky' && !hasNativeKyrgyz()) return formatKyrgyz(date, options)
  try {
    return new Intl.DateTimeFormat(locale, { hourCycle: 'h23', ...options }).format(date)
  } catch {
    return new Intl.DateTimeFormat('ru-RU', options).format(date)
  }
}
