import { AlertCircle, AlertTriangle, Info, PartyPopper, User, Users } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { format, isToday, isYesterday, parseISO } from 'date-fns'
import { ru } from 'date-fns/locale'

import type { BadgeTone } from '@/components/ui/Badge'
import type { NewsAudience, NewsType } from '@/types/news'

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

export const AUDIENCE_META: Record<NewsAudience, { icon: LucideIcon }> = {
  all: { icon: Users },
  selected: { icon: User },
}

/** `2026-09-19T15:30:00Z` → `Сегодня, 15:30` / `Вчера, 18:20` / `19 сентября` — never a long raw datetime. */
export function formatNewsTimestamp(value: string): string {
  const date = parseISO(value)
  if (isToday(date)) return `Сегодня, ${format(date, 'HH:mm')}`
  if (isYesterday(date)) return `Вчера, ${format(date, 'HH:mm')}`
  return format(date, 'd MMMM', { locale: ru })
}

/** News admins sometimes fill `text` with the same words as `title` — skip the description line rather than showing the same sentence twice. */
export function isRedundantNewsText(title: string, text: string): boolean {
  const normalized = (value: string) => value.trim().toLowerCase()
  return normalized(text).length === 0 || normalized(text) === normalized(title)
}
