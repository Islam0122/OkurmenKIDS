import type { ReactNode } from 'react'

import { cn } from '@/utils/cn'

export type BadgeTone = 'success' | 'warning' | 'danger' | 'muted' | 'brand'

const TONE_CLASSES: Record<BadgeTone, string> = {
  success: 'bg-brand-50 text-brand-700',
  warning: 'bg-warning-soft text-warning',
  danger: 'bg-danger-soft text-danger',
  muted: 'bg-surface-hover text-ink-muted border border-border',
  brand: 'bg-brand-500 text-white',
}

export interface BadgeProps {
  tone?: BadgeTone
  children: ReactNode
  className?: string
}

export function Badge({ tone = 'muted', children, className }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium leading-none',
        TONE_CLASSES[tone],
        className,
      )}
    >
      <span className="size-1.5 rounded-full bg-current" aria-hidden />
      {children}
    </span>
  )
}
