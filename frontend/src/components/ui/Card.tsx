import type { ElementType, ReactNode } from 'react'

import { cn } from '@/utils/cn'

export interface CardProps {
  /** Rendered element — `section` for a titled page block, `div` otherwise. */
  as?: ElementType
  title?: ReactNode
  /** Small secondary line under the title. */
  description?: ReactNode
  /** Right-aligned header controls ("Все →", a filter…). */
  actions?: ReactNode
  /** `none` for cards whose content brings its own edge-to-edge layout (tables, lists). */
  padding?: 'default' | 'none'
  className?: string
  children?: ReactNode
}

/**
 * The single card surface of the app: same radius, border, padding
 * (16px phone / 20px desktop) and title typography on every page.
 */
export function Card({ as: Component = 'div', title, description, actions, padding = 'default', className, children }: CardProps) {
  const hasHeader = title || actions
  return (
    <Component className={cn('card min-w-0', padding === 'default' && 'card-body', className)}>
      {hasHeader ? (
        <div className={cn('mb-4 flex items-start justify-between gap-3', padding === 'none' && 'card-body mb-0')}>
          <div className="min-w-0">
            {title ? <h2 className="section-title">{title}</h2> : null}
            {description ? <p className="mt-0.5 text-sm text-ink-secondary">{description}</p> : null}
          </div>
          {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
        </div>
      ) : null}
      {children}
    </Component>
  )
}
