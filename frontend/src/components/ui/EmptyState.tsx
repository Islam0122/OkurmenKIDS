import type { ComponentType, ReactNode } from 'react'
import { Inbox } from 'lucide-react'

import { cn } from '@/utils/cn'

export interface EmptyStateProps {
  title: string
  description?: string
  icon?: ComponentType<{ className?: string }>
  action?: ReactNode
  className?: string
}

export function EmptyState({ title, description, icon: Icon = Inbox, action, className }: EmptyStateProps) {
  return (
    <div className={cn('flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border bg-surface py-14 text-center', className)}>
      <span className="flex size-11 items-center justify-center rounded-full bg-surface-hover text-ink-muted">
        <Icon className="size-5" aria-hidden />
      </span>
      <div>
        <p className="font-medium text-ink">{title}</p>
        {description ? <p className="mt-1 text-sm text-ink-secondary">{description}</p> : null}
      </div>
      {action}
    </div>
  )
}
