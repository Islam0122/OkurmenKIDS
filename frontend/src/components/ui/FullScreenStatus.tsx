import type { ComponentType, ReactNode } from 'react'

import { cn } from '@/utils/cn'

type StatusTone = 'muted' | 'warning' | 'danger'

const TONE_CLASSES: Record<StatusTone, string> = {
  muted: 'bg-surface-hover text-ink-muted',
  warning: 'bg-warning-soft text-warning',
  danger: 'bg-danger-soft text-danger',
}

export interface FullScreenStatusProps {
  icon: ComponentType<{ className?: string }>
  tone?: StatusTone
  title: string
  description?: ReactNode
  actions?: ReactNode
  className?: string
}

/** The shared full-page layout behind 404, access-denied, offline and crash screens — keeps them visually identical. */
export function FullScreenStatus({ icon: Icon, tone = 'muted', title, description, actions, className }: FullScreenStatusProps) {
  return (
    <div className={cn('flex min-h-screen flex-col items-center justify-center gap-4 bg-surface-muted px-4 text-center', className)}>
      <span className={cn('flex size-14 items-center justify-center rounded-full', TONE_CLASSES[tone])}>
        <Icon className="size-6" aria-hidden />
      </span>
      <div>
        <h1 className="text-lg font-semibold text-ink">{title}</h1>
        {description ? <p className="mt-1 max-w-sm text-sm text-ink-secondary">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center justify-center gap-2">{actions}</div> : null}
    </div>
  )
}
