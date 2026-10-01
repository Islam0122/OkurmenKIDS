import type { ReactNode } from 'react'

export interface PageHeaderProps {
  title: ReactNode
  description?: ReactNode
  /** Page-level buttons (export, create…). Wrap below the title on phones. */
  actions?: ReactNode
  /** Small element next to the title, e.g. a status badge. */
  badge?: ReactNode
}

/** The one page title block: title (20px phone / 24px desktop) → description → actions. */
export function PageHeader({ title, description, actions, badge }: PageHeaderProps) {
  return (
    <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <h1 className="min-w-0 text-xl font-semibold text-ink sm:text-2xl">{title}</h1>
          {badge}
        </div>
        {description ? <p className="mt-1 text-sm text-ink-secondary">{description}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  )
}
