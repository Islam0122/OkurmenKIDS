import { AlertCircle, AlertTriangle, Info, PartyPopper } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { format, isToday, isYesterday, parseISO } from 'date-fns'
import { ru } from 'date-fns/locale'

import type { BadgeTone } from '@/components/ui/Badge'
import type { NewsType } from '@/types/news'

export interface NewsTypeMeta {
  icon: LucideIcon
  tone: BadgeTone
  iconClass: string
  bgClass: string
}

export const NEWS_TYPE_META: Record<NewsType, NewsTypeMeta> = {
  info: { icon: Info, tone: 'info', iconClass: 'text-info', bgClass: 'bg-info-soft' },
  important: { icon: AlertCircle, tone: 'danger', iconClass: 'text-danger', bgClass: 'bg-danger-soft' },
  warning: { icon: AlertTriangle, tone: 'warning', iconClass: 'text-warning', bgClass: 'bg-warning-soft' },
  event: { icon: PartyPopper, tone: 'success', iconClass: 'text-brand-700', bgClass: 'bg-brand-50' },
}

/** `2026-09-19T15:30:00Z` → `Сегодня, 15:30` / `Вчера, 12:10` / `19 сентября, 12:10`. */
export function formatNewsTimestamp(value: string): string {
  const date = parseISO(value)
  if (isToday(date)) return `Сегодня, ${format(date, 'HH:mm')}`
  if (isYesterday(date)) return `Вчера, ${format(date, 'HH:mm')}`
  return format(date, 'd MMMM, HH:mm', { locale: ru })
}

/** `2026-09-19T15:30:00Z` → `19 сентября 2026` — used on the full News page. */
export function formatNewsDate(value: string): string {
  return format(parseISO(value), 'd MMMM yyyy', { locale: ru })
}
