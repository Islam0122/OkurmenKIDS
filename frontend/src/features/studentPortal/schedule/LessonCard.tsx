import { Ban, CalendarClock, CheckCircle2, Clock3, Hash, MapPin, Radio, User, UsersRound, XCircle } from 'lucide-react'

import { cn } from '@/utils/cn'
import type { PortalLesson } from '@/types/studentPortal'

import { usePortalI18n } from '../i18n'
import { lessonNo } from '../ui'
import { NO_SUBJECT_ICON, SUBJECT_TONE, durationMin, subjectKind, uiStatus, type UiStatus } from './model'

const STATUS: Record<UiStatus, { tone: string; icon: typeof CheckCircle2 }> = {
  scheduled: { tone: 'bg-info-soft text-info', icon: CalendarClock },
  in_progress: { tone: 'bg-brand-600 text-white shadow-sm shadow-brand-600/30', icon: Radio },
  completed: { tone: 'bg-brand-50 text-brand-700', icon: CheckCircle2 },
  missed: { tone: 'bg-danger-soft text-danger', icon: XCircle },
  cancelled: { tone: 'bg-surface-muted text-ink-secondary ring-1 ring-border', icon: Ban },
}

export function ScheduleStatusBadge({ lesson, className }: { lesson: PortalLesson; className?: string }) {
  const { t } = usePortalI18n()
  const status = uiStatus(lesson)
  const { tone, icon: Icon } = STATUS[status]
  const label = status === 'missed' ? t('schedule.status.missed') : t(`lesson.status.${status}`)
  return (
    <span className={cn('inline-flex items-center gap-1.5 whitespace-nowrap rounded-full py-1 pl-2 pr-2.5 text-xs font-semibold', tone, className)}>
      {status === 'in_progress' ? (
        <span className="relative flex size-2" aria-hidden>
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-white/80 motion-reduce:animate-none" />
          <span className="relative inline-flex size-2 rounded-full bg-white" />
        </span>
      ) : <Icon className="size-3.5" aria-hidden />}
      {label}
    </span>
  )
}

export function SubjectChip({ lesson, className }: { lesson: PortalLesson; className?: string }) {
  const tone = SUBJECT_TONE[subjectKind(lesson)]
  const Icon = lesson.subject ? tone.icon : NO_SUBJECT_ICON
  return (
    <span className={cn('inline-flex min-w-0 items-center gap-1.5 rounded-lg px-2 py-1 text-xs font-bold', tone.chip, className)}>
      <Icon className="size-3.5 shrink-0" aria-hidden />
      <span className="truncate">{lesson.subject?.name ?? lesson.course?.name ?? '—'}</span>
    </span>
  )
}

/**
 * One lesson: subject accent stripe, the time as the headline, «Урок N · тема»,
 * the educational month, then trainer / group / place. `compact` drops the
 * secondary line spacing for the timeline and the month side panel.
 */
export function LessonCard({ lesson, compact = false }: { lesson: PortalLesson; compact?: boolean }) {
  const { t } = usePortalI18n()
  const status = uiStatus(lesson)
  const tone = SUBJECT_TONE[subjectKind(lesson)]
  const minutes = durationMin(lesson)
  const muted = status === 'cancelled'
  const number = lesson.numbering?.number
  const month = lessonNo(t, lesson)
  const place = [lesson.branch?.name, lesson.room ? t('lesson.room', { room: lesson.room.name }) : null].filter(Boolean).join(' · ')

  return (
    <article
      className={cn(
        'sp-card sp-card-hover relative min-w-0 overflow-hidden',
        compact ? 'p-3.5 pl-5' : 'p-4 pl-5 sm:p-5 sm:pl-6',
        status === 'in_progress' && 'ring-2 ring-brand-500/40',
      )}
      aria-label={`${lesson.start ?? ''}–${lesson.end ?? ''} ${lesson.subject?.name ?? ''}`}
    >
      <span className={cn('absolute inset-y-0 left-0 w-1.5', muted ? 'bg-border-strong' : tone.bar)} aria-hidden />

      <div className="flex flex-wrap items-center justify-between gap-2">
        <SubjectChip lesson={lesson} />
        <ScheduleStatusBadge lesson={lesson} />
      </div>

      <div className={cn('flex flex-wrap items-baseline gap-x-2.5 gap-y-0.5', compact ? 'mt-2' : 'mt-3')}>
        <p className={cn('font-extrabold tracking-tight tabular-nums text-ink', compact ? 'text-lg' : 'text-xl sm:text-[22px]', muted && 'text-ink-muted line-through')}>
          {lesson.start ?? '—'}
          {lesson.end ? <span className="font-semibold text-ink-muted"> — {lesson.end}</span> : null}
        </p>
        {minutes ? (
          <span className="inline-flex items-center gap-1 text-xs font-medium text-ink-muted">
            <Clock3 className="size-3" aria-hidden />{t('schedule.minutes', { n: minutes })}
          </span>
        ) : null}
      </div>

      {number || lesson.topic ? (
        <p className={cn('mt-1 text-[15px] font-semibold leading-snug text-ink', compact ? 'line-clamp-1' : 'line-clamp-2', muted && 'text-ink-secondary')}>
          {number ? <span className="text-ink-secondary">{t('lesson.number', { n: number })}{lesson.topic ? ' · ' : ''}</span> : null}
          {lesson.topic}
        </p>
      ) : null}
      {month ? (
        <p className="mt-0.5 inline-flex items-center gap-1 text-xs font-medium text-ink-muted">
          <Hash className="size-3" aria-hidden />{month}
        </p>
      ) : null}

      <dl className={cn('flex flex-wrap gap-x-4 gap-y-1.5 text-[13px] text-ink-secondary', compact ? 'mt-2.5' : 'mt-3.5 border-t border-border/60 pt-3')}>
        {lesson.teacher ? (
          <div className="inline-flex min-w-0 items-center gap-1.5">
            <dt className="sr-only">{t('schedule.teacher')}</dt>
            <User className="size-3.5 shrink-0 text-ink-muted" aria-hidden />
            <dd className="truncate font-medium text-ink">{lesson.teacher.name}</dd>
          </div>
        ) : null}
        {lesson.group ? (
          <div className="inline-flex min-w-0 items-center gap-1.5">
            <dt className="sr-only">{t('schedule.group')}</dt>
            <UsersRound className="size-3.5 shrink-0 text-ink-muted" aria-hidden />
            <dd className="truncate">{lesson.group.name}</dd>
          </div>
        ) : null}
        {place ? (
          <div className="inline-flex min-w-0 items-center gap-1.5">
            <dt className="sr-only">{t('schedule.branch')}</dt>
            <MapPin className="size-3.5 shrink-0 text-ink-muted" aria-hidden />
            <dd className="truncate">{place}</dd>
          </div>
        ) : null}
      </dl>

      {status === 'missed' && lesson.attendance === 'excused' ? (
        <p className="mt-2 text-xs font-medium text-warning">{t('schedule.excused')}</p>
      ) : null}
      {lesson.attendance === 'present' || lesson.attendance === 'late' ? (
        <p className={cn('mt-2 inline-flex items-center gap-1 text-xs font-semibold', lesson.attendance === 'late' ? 'text-warning' : 'text-brand-700')}>
          <CheckCircle2 className="size-3.5" aria-hidden />{t(`att.${lesson.attendance}`)}
        </p>
      ) : null}
      {muted && lesson.cancellation_reason ? (
        <p className="mt-2 rounded-lg bg-surface-muted px-2.5 py-1.5 text-xs text-ink-secondary">{t('schedule.reason', { reason: lesson.cancellation_reason })}</p>
      ) : null}
    </article>
  )
}
