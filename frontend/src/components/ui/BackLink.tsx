import type { ReactNode } from 'react'
import { ArrowLeft } from 'lucide-react'
import { Link } from 'react-router-dom'

import { cn } from '@/utils/cn'

export interface BackLinkProps {
  to: string
  children: ReactNode
  className?: string
}

/**
 * The one "← back to where I came from" link for a page reached from
 * another page's "view X" action (Lesson Detail → Attendance/Homework).
 * Sits above the page title, kept subtle (secondary text, no border/fill)
 * so it reads as navigation rather than a primary action — with generous
 * tap padding so it stays easy to hit on mobile without looking oversized.
 * A plain `<Link>` (push, not replace), so the browser's own Back still
 * behaves normally after using it.
 */
export function BackLink({ to, children, className }: BackLinkProps) {
  return (
    <Link
      to={to}
      className={cn(
        'mb-3 -ml-1.5 inline-flex items-center gap-1.5 rounded-md px-1.5 py-2 text-sm font-medium text-ink-secondary transition-colors hover:text-brand-700',
        className,
      )}
    >
      <ArrowLeft className="size-4 shrink-0" aria-hidden />
      {children}
    </Link>
  )
}
