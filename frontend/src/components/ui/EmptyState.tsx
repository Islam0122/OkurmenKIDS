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
    <div className={cn('card flex flex-col items-center justify-center gap-3 border-dashed px-4 py-12 text-center', className)}>
      <span className="flex size-11 items-center justify-center rounded-full bg-surface-hover text-ink-muted">
        <Icon className="size-5" aria-hidden />
      </span>
      <div>
        <p className="font-medium text-ink">{title}</p>
        {description ? <p className="mx-auto mt-1 max-w-md text-sm text-ink-secondary">{description}</p> : null}
      </div>
      {action}
    </div>
  )
}
