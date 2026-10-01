import type { ReactNode } from 'react'

import { cn } from '@/utils/cn'

export interface StatGridProps {
  children: ReactNode
  /** Max columns on wide screens. */
  columns?: 3 | 4
  className?: string
}

/** The one KPI/stat card grid: 1 column on phones, 2 on tablets, 3–4 on desktop. */
export function StatGrid({ children, columns = 4, className }: StatGridProps) {
  return (
    <div
      className={cn(
        'grid grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-4 lg:grid-cols-3',
        columns === 4 && 'xl:grid-cols-4',
        className,
      )}
    >
      {children}
    </div>
  )
}
