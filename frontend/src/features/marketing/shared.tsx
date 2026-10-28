import type { ComponentType, ReactNode } from 'react'
import { format, parseISO } from 'date-fns'
import { ru } from 'date-fns/locale'

import type { BadgeTone } from '@/components/ui/Badge'
import type { Channel, ContentStatus, TaskPriority, TaskStatus } from '@/types/marketing'
import { cn } from '@/utils/cn'

export const CONTENT_TONE: Record<ContentStatus, BadgeTone> = {
  idea: 'muted',
  preparing: 'info',
  review: 'warning',
  scheduled: 'brand',
  published: 'success',
}

/** Цвет полосы статуса в календаре (левая граница карточки публикации). */
export const CONTENT_BORDER: Record<ContentStatus, string> = {
  idea: 'border-l-border-strong',
  preparing: 'border-l-info',
  review: 'border-l-warning',
  scheduled: 'border-l-brand-500',
  published: 'border-l-brand-700',
}

export const TASK_TONE: Record<TaskStatus, BadgeTone> = {
  todo: 'muted',
  in_progress: 'info',
  done: 'success',
}

export const PRIORITY_TONE: Record<TaskPriority, BadgeTone> = {
  low: 'muted',
  medium: 'info',
  high: 'danger',
}

/** Короткое имя канала для тесных мест (ячейка календаря на ноутбуке). */
export const CHANNEL_SHORT: Record<Channel, string> = {
  instagram: 'IG',
  tiktok: 'TT',
  facebook: 'FB',
  telegram: 'TG',
  youtube: 'YT',
  whatsapp: 'WA',
  website: 'Сайт',
  other: '—',
}

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1)
}

/** `2026-10-28` → `Среда, 28 октября 2026`. */
export function longDate(iso: string): string {
  return capitalize(format(parseISO(iso), 'EEEE, d MMMM yyyy', { locale: ru }))
}

/** `2026-10-28` → `28 окт`; с днём недели — `ср, 28 окт`. */
export function shortDate(iso: string, weekday = false): string {
  return format(parseISO(iso), weekday ? 'EEEEEE, d MMM' : 'd MMM', { locale: ru }).replace('.', '')
}

/** `2026-10` → `Октябрь 2026`. */
export function monthLabel(iso: string): string {
  return capitalize(format(parseISO(iso), 'LLLL yyyy', { locale: ru }))
}

/** `2026-10-05`, `2026-10-11` → `5–11 окт 2026` (без года — `5–11 окт`). */
export function rangeLabel(from: string, to: string, withYear = true): string {
  const a = parseISO(from)
  const end = format(parseISO(to), withYear ? 'd MMM yyyy' : 'd MMM', { locale: ru }).replace('.', '')
  return a.getMonth() === parseISO(to).getMonth() ? `${format(a, 'd')}–${end}` : `${shortDate(from)} – ${end}`
}

/** `18:30:00` → `18:30`. */
export function hhmm(value: string | null): string {
  return value ? value.slice(0, 5) : ''
}

/** Дата в формате API без сдвига пояса браузера. */
export function isoDate(date: Date): string {
  return format(date, 'yyyy-MM-dd')
}

export function Field({ id, label, required, hint, className, children }: { id: string; label: string; required?: boolean; hint?: string; className?: string; children: ReactNode }) {
  return (
    <div className={className}>
      <label htmlFor={id} className="mb-1.5 block field-label">
        {label}
        {required ? ' *' : ''}
      </label>
      {children}
      {hint ? <p className="mt-1 text-xs text-ink-muted">{hint}</p> : null}
    </div>
  )
}

export function FormError({ message }: { message: string | null }) {
  return message ? <p className="rounded-xl bg-danger-soft px-3 py-2 text-sm text-danger" role="alert">{message}</p> : null
}

const METRIC_TONE = {
  default: 'bg-brand-50 text-brand-600',
  warning: 'bg-warning-soft text-warning',
  danger: 'bg-danger-soft text-danger',
  info: 'bg-info-soft text-info',
} as const

/** Компактная плитка показателя: две в ряд на телефоне, четыре на ноутбуке. */
export function Metric({ label, value, hint, icon: Icon, tone = 'default' }: {
  label: string
  value: ReactNode
  hint?: string
  icon?: ComponentType<{ className?: string }>
  tone?: keyof typeof METRIC_TONE
}) {
  return (
    <div className="card min-w-0 p-3 transition-shadow hover:shadow-sm sm:p-4">
      <div className="flex items-start justify-between gap-2">
        <p className="min-w-0 text-xs leading-snug text-ink-secondary sm:text-sm">{label}</p>
        {Icon ? (
          <span className={cn('hidden size-8 shrink-0 items-center justify-center rounded-lg sm:flex', METRIC_TONE[tone])}>
            <Icon className="size-4" aria-hidden />
          </span>
        ) : null}
      </div>
      <p className={cn('mt-1 text-2xl font-semibold tabular-nums', tone === 'danger' && value ? 'text-danger' : 'text-ink')}>{value}</p>
      {hint ? <p className="mt-0.5 text-xs text-ink-muted">{hint}</p> : null}
    </div>
  )
}

export function MetricGrid({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">{children}</div>
}

/** Полоса «сделано из запланированного»: одна серия, значения — текстом рядом. */
export function ProgressBar({ value, total, label }: { value: number; total: number; label: string }) {
  const ratio = total > 0 ? Math.min(1, value / total) : 0
  return (
    <div
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={total}
      aria-valuenow={value}
      title={`${label}: ${value} из ${total}`}
      className="h-2 w-full overflow-hidden rounded-full bg-brand-50"
    >
      <div className="h-full rounded-full bg-brand-500 transition-[width] duration-500" style={{ width: `${ratio * 100}%` }} />
    </div>
  )
}
