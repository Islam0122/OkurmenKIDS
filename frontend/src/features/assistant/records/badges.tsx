import { Badge } from '@/components/ui/Badge'
import type { BadgeTone } from '@/components/ui/Badge'
import type { AttendanceStatus, ControlStatus, HomeworkState } from '@/types/assistant'
import { cn } from '@/utils/cn'

/** Read-only status badges and the one percent bar of the Assistant's records. */

const ATTENDANCE: Record<AttendanceStatus, { tone: BadgeTone; label: string }> = {
  present: { tone: 'success', label: 'Присутствовал' },
  late: { tone: 'warning', label: 'Опоздал' },
  absent: { tone: 'danger', label: 'Отсутствовал' },
  excused: { tone: 'info', label: 'Уважительная' },
}

export function AttendanceBadge({ status }: { status: AttendanceStatus | null }) {
  if (!status) return <Badge tone="muted">Не отмечен</Badge>
  return <Badge tone={ATTENDANCE[status].tone}>{ATTENDANCE[status].label}</Badge>
}

const HOMEWORK: Record<HomeworkState, BadgeTone> = { open: 'muted', review: 'info', complete: 'success', missing: 'warning' }

export function HomeworkStateBadge({ status, label }: { status: HomeworkState; label: string }) {
  return <Badge tone={HOMEWORK[status]}>{label}</Badge>
}

const SUBMISSION: Record<'done' | 'review' | 'not_done' | 'waiting', BadgeTone> = { done: 'success', review: 'info', not_done: 'danger', waiting: 'muted' }

export function SubmissionBadge({ state, label }: { state: keyof typeof SUBMISSION; label: string }) {
  return <Badge tone={SUBMISSION[state]}>{label}</Badge>
}

const CONTROL: Record<ControlStatus, BadgeTone> = { normal: 'success', attention: 'warning', low: 'danger', risk: 'danger', no_data: 'muted' }

export function ControlStatusBadge({ status, label }: { status: ControlStatus; label: string }) {
  return <Badge tone={CONTROL[status]} className={status === 'risk' ? 'font-semibold' : undefined}>{label}</Badge>
}

/** Bar colour follows the same bands as «Контроль» (80 / 60). */
export function percentTone(value: number | null): string {
  if (value === null) return 'bg-border-strong'
  if (value >= 80) return 'bg-brand-500'
  if (value >= 60) return 'bg-warning'
  return 'bg-danger'
}

export function PercentBar({ value, className }: { value: number | null; className?: string }) {
  return (
    <div className={cn('h-1.5 w-full overflow-hidden rounded-full bg-surface-hover', className)} role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={value ?? 0}>
      <div className={cn('h-full rounded-full transition-[width]', percentTone(value))} style={{ width: `${Math.max(0, Math.min(value ?? 0, 100))}%` }} />
    </div>
  )
}

export function Percent({ value, className }: { value: number | null; className?: string }) {
  if (value === null) return <span className={cn('text-ink-muted', className)}>—</span>
  return (
    <span className={cn('tabular-nums', value >= 80 ? 'text-ink' : value >= 60 ? 'text-warning' : 'text-danger', className)}>{value}%</span>
  )
}
