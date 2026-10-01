import type { ReactNode } from 'react'

import { cn } from '@/utils/cn'

/**
 * The one filter row above a list/table. Phones: every control full-width,
 * stacked. From `sm` up: controls wrap in a row at a fixed width (see
 * FilterField), so filters look the same on every page.
 */
export function FilterBar({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('mb-6 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end', className)}>{children}</div>
}

export interface FilterFieldProps {
  children: ReactNode
  /** `search` is wider than a plain select. */
  size?: 'md' | 'lg'
  label?: string
  htmlFor?: string
  className?: string
}

export function FilterField({ children, size = 'md', label, htmlFor, className }: FilterFieldProps) {
  return (
    <div className={cn('w-full min-w-0', size === 'lg' ? 'sm:w-72' : 'sm:w-52', className)}>
      {label ? (
        <label htmlFor={htmlFor} className="mb-1.5 block field-label">
          {label}
        </label>
      ) : null}
      {children}
    </div>
  )
}
