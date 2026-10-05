import type { ReactNode } from 'react'
import { format } from 'date-fns'
import { Link } from 'react-router-dom'

import { Badge } from '@/components/ui/Badge'
import type { BadgeTone } from '@/components/ui/Badge'
import type { GroupStatus, StudentStatus } from '@/types/assistant'
import { cn } from '@/utils/cn'

/** Shared bits of the Assistant Workspace pages and modals. */

export const STUDENT_STATUS_TONE: Record<StudentStatus, BadgeTone> = {
  active: 'success',
  paused: 'warning',
  withdrawn: 'danger',
  completed: 'muted',
}

export const GROUP_STATUS_TONE: Record<GroupStatus, BadgeTone> = {
  active: 'success',
  paused: 'warning',
  completed: 'muted',
  cancelled: 'danger',
}

export function StudentStatusBadge({ status, label }: { status: StudentStatus; label: string }) {
  return <Badge tone={STUDENT_STATUS_TONE[status]}>{label}</Badge>
}

export function GroupStatusBadge({ status, label }: { status: GroupStatus; label: string }) {
  return <Badge tone={GROUP_STATUS_TONE[status]}>{label}</Badge>
}

/** A labelled form control with its validation message. */
export function Field({
  label,
  htmlFor,
  required,
  error,
  hint,
  children,
  className,
}: {
  label: string
  htmlFor?: string
  required?: boolean
  error?: string | null
  hint?: string
  children: ReactNode
  className?: string
}) {
  return (
    <div className={cn('min-w-0', className)}>
      <label htmlFor={htmlFor} className="mb-1.5 block text-sm font-medium text-ink">
        {label}
        {required ? <span className="ml-0.5 text-danger">*</span> : null}
      </label>
      {children}
      {error ? <p className="mt-1 text-xs text-danger">{error}</p> : hint ? <p className="mt-1 text-xs text-ink-secondary">{hint}</p> : null}
    </div>
  )
}

/** An inline error block inside a modal/form (the API's own message). */
export function FormError({ message }: { message: string | null | undefined }) {
  if (!message) return null
  return (
    <div role="alert" className="rounded-lg border border-danger/20 bg-danger-soft px-3 py-2 text-sm text-danger">
      {message}
    </div>
  )
}

/** Footer row of a modal form: secondary action left of the primary one; full-width on phones. */
export function ModalActions({ children }: { children: ReactNode }) {
  return <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">{children}</div>
}

/** A key → value row of an overview card. */
export function InfoRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2 text-sm">
      <dt className="shrink-0 text-ink-secondary">{label}</dt>
      <dd className="min-w-0 text-right font-medium text-ink">{children || '—'}</dd>
    </div>
  )
}

export function todayIso(): string {
  return format(new Date(), 'yyyy-MM-dd')
}

const LINK_VARIANTS = {
  primary: 'bg-brand-500 text-white hover:bg-brand-600',
  secondary: 'border border-brand-200 bg-surface text-brand-700 hover:bg-brand-50',
} as const

/** A link that looks like a Button (never a <button> inside an <a>). */
export function ButtonLink({ to, icon, variant = 'primary', children, className }: {
  to: string
  icon?: ReactNode
  variant?: keyof typeof LINK_VARIANTS
  children: ReactNode
  className?: string
}) {
  return (
    <Link to={to} className={cn('inline-flex h-10 shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-lg px-4 text-sm font-medium transition-colors', LINK_VARIANTS[variant], className)}>
      {icon}
      {children}
    </Link>
  )
}
