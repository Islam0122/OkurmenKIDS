import type { ComponentType, ReactNode } from 'react'
import { AlertCircle, CalendarOff, Check, Minus, X } from 'lucide-react'

import type { CellCode, MatrixHomework, WarningLevel } from '@/types/attendanceMatrix'
import { cn } from '@/utils/cn'

/** One colour system for the matrix, the legend, the cards and the modal. */
export const CELL_STYLE: Record<CellCode, { label: string; box: string; icon: ComponentType<{ className?: string }> | null }> = {
  done: { label: 'Присутствовал + сдал ДЗ', box: 'bg-brand-500 text-white', icon: Check },
  partial: { label: 'Присутствовал (без ДЗ)', box: 'bg-brand-100 text-brand-700', icon: Check },
  excused: { label: 'Уважительная причина', box: 'bg-[#f6d365] text-[#6b4a00]', icon: AlertCircle },
  absent: { label: 'Не пришёл без причины', box: 'bg-danger text-white', icon: X },
  empty: { label: 'Нет данных', box: 'bg-surface-hover text-ink-muted', icon: Minus },
  planned: { label: 'Занятие ещё не прошло', box: 'border border-dashed border-border-strong bg-surface text-ink-muted', icon: null },
  no_lesson: { label: 'Нет занятия', box: 'bg-surface-muted text-ink-muted/60', icon: CalendarOff },
}

export const LEGEND_ORDER: CellCode[] = ['done', 'partial', 'excused', 'absent', 'empty', 'no_lesson']

export const HOMEWORK_LABEL: Record<MatrixHomework, string> = {
  done: 'Сдано',
  missed: 'Не сдано',
  pending: 'Ещё не срок',
  none: 'ДЗ не задано',
}

export const LEVEL_STYLE: Record<WarningLevel, { label: string; text: string; bg: string; dot: string }> = {
  critical: { label: 'Критично', text: 'text-danger', bg: 'bg-danger-soft', dot: 'bg-danger' },
  attention: { label: 'Внимание', text: 'text-warning', bg: 'bg-warning-soft', dot: 'bg-warning' },
  warning: { label: 'Предупреждение', text: 'text-[#8a6d00]', bg: 'bg-[#fff8e1]', dot: 'bg-[#e0b400]' },
}

export function CellIcon({ code, size = 'md', className }: { code: CellCode; size?: 'sm' | 'md'; className?: string }) {
  const style = CELL_STYLE[code]
  const Icon = style.icon
  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center justify-center rounded-md',
        size === 'md' ? 'size-7' : 'size-5',
        style.box,
        className,
      )}
    >
      {Icon ? <Icon className={cn(size === 'md' ? 'size-4' : 'size-3', 'stroke-[2.5]')} aria-hidden /> : null}
    </span>
  )
}

export function Legend({ codes = LEGEND_ORDER }: { codes?: CellCode[] }) {
  return (
    <ul className="flex flex-wrap gap-x-5 gap-y-2" aria-label="Обозначения">
      {codes.map((code) => (
        <li key={code} className="flex items-center gap-2 text-sm text-ink-secondary">
          <CellIcon code={code} size="sm" />
          {CELL_STYLE[code].label}
        </li>
      ))}
    </ul>
  )
}

export function pct(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : `${value}%`
}

export function percentTone(value: number | null | undefined): string {
  if (value === null || value === undefined) return 'text-ink-muted'
  if (value >= 85) return 'text-brand-700'
  if (value >= 70) return 'text-warning'
  return 'text-danger'
}

export function SummaryCard({
  icon,
  label,
  value,
  hint,
  tone,
}: {
  icon: ReactNode
  label: string
  value: ReactNode
  hint?: ReactNode
  tone: 'green' | 'yellow' | 'red' | 'gray'
}) {
  const ring = { green: 'bg-brand-50', yellow: 'bg-[#fff6d6]', red: 'bg-danger-soft', gray: 'bg-surface-hover' }[tone]
  return (
    <div className="card flex items-center gap-4 p-4">
      <span className={cn('flex size-12 shrink-0 items-center justify-center rounded-full', ring)}>{icon}</span>
      <div className="min-w-0">
        <p className="truncate text-sm text-ink-secondary">{label}</p>
        <p className="text-2xl font-semibold leading-tight text-ink">{value}</p>
        {hint ? <p className="text-sm text-ink-muted">{hint}</p> : null}
      </div>
    </div>
  )
}

export function WarningDot({ level, title }: { level: WarningLevel; title: string }) {
  return (
    <span title={title} className={cn('inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[11px] font-semibold', LEVEL_STYLE[level].bg, LEVEL_STYLE[level].text)}>
      <span className={cn('size-1.5 rounded-full', LEVEL_STYLE[level].dot)} aria-hidden />
      {LEVEL_STYLE[level].label}
    </span>
  )
}

/** Shift an ISO date by a number of months, clamped to the 1st. */
export function monthAnchor(iso: string): string {
  return `${iso.slice(0, 7)}-01`
}

export function todayIso(): string {
  const now = new Date()
  const offset = now.getTimezoneOffset() * 60_000
  return new Date(now.getTime() - offset).toISOString().slice(0, 10)
}

export function shortDate(iso: string): string {
  return `${iso.slice(8, 10)}.${iso.slice(5, 7)}`
}

export function formatDateTime(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}
