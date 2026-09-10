import type { ComponentType } from 'react'

import { cn } from '@/utils/cn'

export interface StatCardProps {
  label: string
  value: string | number
  icon?: ComponentType<{ className?: string }>
  hint?: string
  tone?: 'default' | 'warning' | 'danger'
  className?: string
}

const TONE_ICON_CLASSES: Record<NonNullable<StatCardProps['tone']>, string> = {
  default: 'bg-brand-50 text-brand-600',
  warning: 'bg-warning-soft text-warning',
  danger: 'bg-danger-soft text-danger',
}

export function StatCard({ label, value, icon: Icon, hint, tone = 'default', className }: StatCardProps) {
  return (
    <div className={cn('rounded-xl border border-border bg-surface p-4', className)}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm text-ink-secondary">{label}</p>
          <p className="mt-1 text-2xl font-semibold text-ink">{value}</p>
          {hint ? <p className="mt-1 text-xs text-ink-muted">{hint}</p> : null}
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
