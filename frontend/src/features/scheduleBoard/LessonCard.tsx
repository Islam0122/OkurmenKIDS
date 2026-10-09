import type { CSSProperties } from 'react'
import { AlertTriangle, Ban, CheckCircle2, CirclePlay } from 'lucide-react'

import type { BoardLesson } from '@/types/schedule'
import { cn } from '@/utils/cn'

import { formatDuration } from './timeGrid'

const NEUTRAL = '#94A3B8'

/** A trainer's color as the card's accent stripe, its light tint as the
 * background — the text itself stays dark ink, readable on every color. */
export function trainerStyle(color: string | null | undefined, status?: string): CSSProperties {
  const accent = status === 'cancelled' ? NEUTRAL : color || NEUTRAL
  return {
    borderLeftColor: accent,
    backgroundColor: `color-mix(in srgb, ${accent} ${status === 'completed' ? 8 : 13}%, white)`,
  }
}

export function TrainerDot({ color, className }: { color: string | null | undefined; className?: string }) {
  return <span aria-hidden className={cn('inline-block size-2.5 shrink-0 rounded-full', className)} style={{ backgroundColor: color || NEUTRAL }} />
}

export function StatusIcon({ status }: { status: BoardLesson['status'] }) {
  if (status === 'completed') return <CheckCircle2 className="size-3.5 shrink-0 text-brand-600" aria-label="Проведён" />
  if (status === 'in_progress') return <CirclePlay className="size-3.5 shrink-0 text-info" aria-label="Идёт занятие" />
  if (status === 'cancelled') return <Ban className="size-3.5 shrink-0 text-ink-muted" aria-label="Отменён" />
  return null
}

export function lessonLabel(lesson: BoardLesson): string {
  return [
    `${lesson.start}–${lesson.end} (${formatDuration(lesson.duration_minutes)})`,
    lesson.group.name,
    lesson.subject?.name,
    `Тренер: ${lesson.teacher?.name ?? '—'}`,
    `Кабинет: ${lesson.room?.name ?? 'не указан'}`,
    lesson.status_display,
    ...lesson.conflicts.map((c) => `Конфликт: ${c.message}`),
  ].filter(Boolean).join(' · ')
}

/**
 * One lesson in the grid. `density` follows the card's height on screen:
 * a 30-minute lesson shows time + group, a 1.5-hour one everything.
 */
export function LessonCard({
  lesson,
  onOpen,
  density = 'full',
  showRoom = true,
  className,
  style,
}: {
  lesson: BoardLesson
  onOpen: (lesson: BoardLesson) => void
  density?: 'tiny' | 'compact' | 'full'
  showRoom?: boolean
  className?: string
  style?: CSSProperties
}) {
  const conflict = lesson.conflicts.length > 0
  return (
    <button
      type="button"
      onClick={(event) => {
        event.stopPropagation()
        onOpen(lesson)
      }}
      title={lessonLabel(lesson)}
      aria-label={lessonLabel(lesson)}
      data-lesson-id={lesson.id}
      className={cn(
        'group/card flex min-w-0 flex-col overflow-hidden rounded-md border border-l-[3px] border-black/5 px-1.5 text-left text-ink shadow-xs transition',
        'hover:z-20 hover:shadow-md focus-visible:z-20 focus-visible:outline-2 focus-visible:outline-brand-500',
        density === 'tiny' ? 'justify-center py-0' : 'py-1',
        lesson.status === 'cancelled' && 'opacity-60',
        conflict && 'ring-2 ring-danger/70',
        className,
      )}
      style={{ ...trainerStyle(lesson.teacher?.color, lesson.status), ...style }}
    >
      <span className="flex min-w-0 items-center gap-1">
        {conflict ? <AlertTriangle className="size-3.5 shrink-0 text-danger" aria-hidden /> : null}
        <span className="shrink-0 text-2xs font-semibold tabular-nums text-ink-secondary">{lesson.start}–{lesson.end}</span>
        {density === 'tiny' ? <span className={cn('truncate text-xs font-semibold', lesson.status === 'cancelled' && 'line-through')}>{lesson.group.name}</span> : null}
        <span className="ml-auto"><StatusIcon status={lesson.status} /></span>
      </span>
      {density !== 'tiny' ? (
        <>
          <span className={cn('truncate text-xs font-semibold leading-tight sm:text-sm', lesson.status === 'cancelled' && 'line-through')}>{lesson.group.name}</span>
          <span className="truncate text-2xs leading-tight text-ink-secondary sm:text-xs">
            {lesson.teacher?.name ?? 'Тренер не указан'}
            {showRoom && lesson.room ? ` · ${lesson.room.name}` : ''}
          </span>
        </>
      ) : null}
      {density === 'full' ? (
        <span className="truncate text-2xs leading-tight text-ink-muted">
          {formatDuration(lesson.duration_minutes)}
          {lesson.subject ? ` · ${lesson.subject.name}` : ''}
          {lesson.status !== 'scheduled' ? ` · ${lesson.status_display}` : ''}
        </span>
      ) : null}
    </button>
  )
}
