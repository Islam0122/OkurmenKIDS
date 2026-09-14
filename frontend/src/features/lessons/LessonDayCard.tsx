import { CheckCircle2, FileText, Loader2, XCircle, Youtube } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Badge } from '@/components/ui/Badge'
import type { BadgeTone } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import type { Lesson } from '@/types/academy'
import { formatTimeRange } from '@/utils/format'

import { hasLessonPassed } from './lessonViews'

const STATUS_TONE: Record<Lesson['status'], BadgeTone> = {
  scheduled: 'muted',
  in_progress: 'warning',
  completed: 'success',
  cancelled: 'danger',
}

export interface LessonDayCardProps {
  lesson: Lesson
  studentsCount?: number
  /** Only meaningful — and only fetched by the caller — once the lesson has happened. */
  attendanceFilled?: boolean
  homeworkCount?: number
  isEnriching?: boolean
}

/**
 * The detailed "Today"/"Tomorrow" row: what a Trainer needs to act on one
 * lesson without opening it first. The badge always reflects the real
 * `Lesson.status` (never inferred from the clock) — the one exception is a
 * still-`scheduled` lesson whose slot is already over, shown as "Требует
 * внимания" since the trainer never explicitly started/finished it (see
 * `needsAttentionCheck` — this is the same "requires attention" concept the
 * Admin dashboard's KPI uses, computed here from the same real status).
 */
export function LessonDayCard({ lesson, studentsCount, attendanceFilled, homeworkCount, isEnriching }: LessonDayCardProps) {
  const isCancelled = lesson.status === 'cancelled'
  const isCompleted = lesson.status === 'completed'
  const isInProgress = lesson.status === 'in_progress'
  const needsAttentionCheck = !isCancelled && !isCompleted && (isInProgress || hasLessonPassed(lesson))
  const hasMaterials = Boolean(lesson.youtube_url) || lesson.presentation_urls.length > 0

  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-mono text-sm font-semibold text-ink">{formatTimeRange(lesson.start_time, lesson.end_time)}</p>
          <p className="mt-1 text-sm font-medium text-ink">{lesson.group_name}</p>
          <p className="text-sm text-ink-secondary">
            {lesson.subject_name ?? 'Без предмета'} · Урок #{lesson.lesson_number}
            {lesson.topic ? <span> — {lesson.topic}</span> : null}
          </p>
          <p className="mt-1 text-xs text-ink-muted">
            {lesson.room_name ? `${lesson.room_name} · ` : ''}
            {studentsCount !== undefined ? `${studentsCount} студентов` : null}
          </p>
        </div>

        {isCancelled ? (
          <Badge tone={STATUS_TONE.cancelled}>Отменено</Badge>
        ) : isCompleted ? (
          <Badge tone={STATUS_TONE.completed}>{lesson.status_display}</Badge>
        ) : isInProgress ? (
          <Badge tone={STATUS_TONE.in_progress}>Идёт занятие</Badge>
        ) : hasLessonPassed(lesson) ? (
          <Badge tone="danger">Требует внимания</Badge>
        ) : (
          <Badge tone="muted">Предстоит</Badge>
        )}
      </div>

      {isCancelled ? (
        lesson.cancellation_reason ? (
          <p className="mt-3 rounded-lg bg-danger-soft px-3 py-2 text-xs text-danger">Причина: {lesson.cancellation_reason}</p>
        ) : null
      ) : needsAttentionCheck ? (
        <div className="mt-3 space-y-1 text-sm">
          {isEnriching ? (
            <p className="flex items-center gap-1.5 text-ink-muted">
              <Loader2 className="size-3.5 animate-spin" aria-hidden /> Проверяем статус…
            </p>
          ) : (
            <>
              <ChecklistLine ok={attendanceFilled === true} okText="Посещаемость заполнена" missingText="Посещаемость не отмечена" />
              <ChecklistLine
                ok={(homeworkCount ?? 0) > 0}
                okText="Домашнее задание добавлено"
                missingText="ДЗ не добавлено"
              />
            </>
          )}
        </div>
      ) : hasMaterials ? (
        <p className="mt-3 flex items-center gap-1.5 text-xs text-ink-secondary">
          {lesson.youtube_url ? <Youtube className="size-3.5" aria-hidden /> : <FileText className="size-3.5" aria-hidden />}
          Материалы к уроку готовы
        </p>
      ) : null}

      <div className="mt-3">
        <Link to={`/app/lessons/${lesson.id}`}>
          <Button size="sm" variant={isCancelled ? 'secondary' : 'primary'}>
            Открыть урок
          </Button>
        </Link>
      </div>
    </div>
  )
}

function ChecklistLine({ ok, okText, missingText }: { ok: boolean; okText: string; missingText: string }) {
  const Icon = ok ? CheckCircle2 : XCircle
  return (
    <p className={ok ? 'flex items-center gap-1.5 text-brand-700' : 'flex items-center gap-1.5 text-danger'}>
      <Icon className="size-4 shrink-0" aria-hidden />
      {ok ? okText : missingText}
    </p>
  )
}
