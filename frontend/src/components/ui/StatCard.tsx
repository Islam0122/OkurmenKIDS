import type { ComponentType } from 'react'
import { Minus, TrendingDown, TrendingUp } from 'lucide-react'

import { cn } from '@/utils/cn'

export interface StatCardTrend {
  /** "up" | "down" | "stable" — the raw numeric direction (see backend's
   * ComparisonMetric.trend), not yet judged as good/bad. */
  direction: 'up' | 'down' | 'stable'
  /** e.g. `change_percent` from the backend metric — shown as "+8%"/"-4.2%". */
  changePercent: number | null
  /** Which raw direction counts as an improvement for *this* metric — a
   * rising `cancelled_lessons` is "up" but bad news, so the color is never
   * inferred from `direction` alone (spec §8: "do NOT blindly treat 'up' as
   * good"). Defaults to "up" (the common case: more is better). */
  goodDirection?: 'up' | 'down'
}

export interface StatCardProps {
  label: string
  value: string | number
  icon?: ComponentType<{ className?: string }>
  hint?: string
  tone?: 'default' | 'warning' | 'danger'
  trend?: StatCardTrend
  className?: string
}

const TONE_ICON_CLASSES: Record<NonNullable<StatCardProps['tone']>, string> = {
  default: 'bg-brand-50 text-brand-600',
  warning: 'bg-warning-soft text-warning',
  danger: 'bg-danger-soft text-danger',
}

function TrendBadge({ trend }: { trend: StatCardTrend }) {
  const { direction, changePercent, goodDirection = 'up' } = trend
  if (direction === 'stable' || changePercent === null) {
    return (
      <span className="inline-flex items-center gap-0.5 text-xs font-medium text-ink-muted">
        <Minus className="size-3" /> 0%
      </span>
    )
  }
  const isGood = direction === goodDirection
  const Icon = direction === 'up' ? TrendingUp : TrendingDown
  return (
    <span
      className={cn(
        'inline-flex items-center gap-0.5 text-xs font-medium',
        isGood ? 'text-brand-600' : 'text-danger',
      )}
    >
      <Icon className="size-3" />
      {changePercent > 0 ? '+' : ''}
      {changePercent}%
    </span>
  )
}

export function StatCard({ label, value, icon: Icon, hint, tone = 'default', trend, className }: StatCardProps) {
  return (
    <div className={cn('rounded-xl border border-border bg-surface p-4', className)}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm text-ink-secondary">{label}</p>
          <p className="mt-1 text-2xl font-semibold text-ink">{value}</p>
          <div className="mt-1 flex items-center gap-2">
            {hint ? <p className="text-xs text-ink-muted">{hint}</p> : null}
            {trend ? <TrendBadge trend={trend} /> : null}
          </div>
        </div>
        {Icon ? (
          <span className={cn('flex size-10 shrink-0 items-center justify-center rounded-lg', TONE_ICON_CLASSES[tone])}>
            <Icon className="size-5" />
          </span>
        ) : null}
      </div>
    </div>
  )
}
