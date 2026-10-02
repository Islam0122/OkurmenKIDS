import { format, parseISO } from 'date-fns'

import { Badge, type BadgeTone } from '@/components/ui/Badge'
import type { ExamSession, ParticipantStatus, SessionPhase } from '@/types/exams'
import { cn } from '@/utils/cn'

export const PHASE_TONE: Record<SessionPhase, BadgeTone> = {
  draft: 'muted',
  scheduled: 'info',
  active: 'success',
  finished: 'muted',
  cancelled: 'danger',
}

export const PARTICIPANT_LABEL: Record<ParticipantStatus, string> = {
  not_started: 'Не начал',
  in_progress: 'Проходит экзамен',
  paused: 'Приостановлен',
  disconnected: 'Нет соединения',
  completed: 'Завершил',
  expired: 'Время истекло',
}

export const PARTICIPANT_TONE: Record<ParticipantStatus, BadgeTone> = {
  not_started: 'muted',
  in_progress: 'success',
  paused: 'warning',
  disconnected: 'warning',
  completed: 'info',
  expired: 'danger',
}

const DOT_CLASS: Record<ParticipantStatus, string> = {
  not_started: 'bg-ink-muted/40',
  in_progress: 'bg-brand-500',
  paused: 'bg-warning',
  disconnected: 'bg-warning',
  completed: 'bg-info',
  expired: 'bg-danger',
}

/** A status dot (SVG-free, decorative — the label next to it carries the meaning). */
export function StatusDot({ status, className }: { status: ParticipantStatus; className?: string }) {
  return <span aria-hidden className={cn('inline-block size-2 shrink-0 rounded-full', DOT_CLASS[status], className)} />
}

export function ParticipantStatusBadge({ status }: { status: ParticipantStatus }) {
  return (
    <Badge tone={PARTICIPANT_TONE[status]}>{PARTICIPANT_LABEL[status]}</Badge>
  )
}

/** «Идёт сейчас» — a pulsing live dot (pulse off for reduced motion).
 * `label={false}` renders the dot alone (when the text next to it says it). */
export function LiveIndicator({
  paused = false,
  label = true,
  className,
}: {
  paused?: boolean
  label?: boolean
  className?: string
}) {
  return (
    <span className={cn('inline-flex items-center gap-2 text-sm font-semibold', paused ? 'text-warning' : 'text-danger', className)}>
      <span className="relative flex size-2.5" aria-hidden>
        {paused ? null : (
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-danger opacity-60 motion-reduce:animate-none" />
        )}
        <span className={cn('relative inline-flex size-2.5 rounded-full', paused ? 'bg-warning' : 'bg-danger')} />
      </span>
      {label ? (paused ? 'На паузе' : 'Идёт сейчас') : null}
    </span>
  )
}

export function PhaseBadge({ session }: { session: ExamSession }) {
  if (session.is_live) return <LiveIndicator paused={session.is_paused} />
  return <Badge tone={PHASE_TONE[session.phase]}>{session.phase_label}</Badge>
}

/** `02.10.2026` */
export function formatSessionDate(session: ExamSession): string | null {
  const start = session.scheduled_start ?? session.started_at
  return start ? format(parseISO(start), 'dd.MM.yyyy') : null
}

/** `14:00–15:00` (local time). */
export function formatSessionTime(session: ExamSession): string | null {
  const start = session.scheduled_start ?? session.started_at
  if (!start) return null
  const end = session.scheduled_end ?? session.ends_at
  return end ? `${format(parseISO(start), 'HH:mm')}–${format(parseISO(end), 'HH:mm')}` : format(parseISO(start), 'HH:mm')
}

/** `2832` → `47:12`, `null` → `—`. */
export function formatDuration(seconds: number | null): string {
  if (seconds === null) return '—'
  const total = Math.max(0, Math.round(seconds))
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const secs = total % 60
  const mmss = `${String(minutes).padStart(hours ? 2 : 1, '0')}:${String(secs).padStart(2, '0')}`
  return hours ? `${hours}:${mmss}` : mmss
}

export function formatClock(value: string | null): string {
  return value ? format(parseISO(value), 'HH:mm') : '—'
}
