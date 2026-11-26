import { Layers } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Badge } from '@/components/ui/Badge'
import type { Lesson } from '@/types/academy'
import { cn } from '@/utils/cn'
import { formatTimeRange } from '@/utils/format'

import { LESSON_STATUS_TONE } from './lessonStatus'

export interface LessonCardProps {
  lesson: Lesson
  compact?: boolean
  className?: string
}

export function LessonCard({ lesson, compact = false, className }: LessonCardProps) {
  return (
    <Link
      // A parallel session's group lesson opens the shared session (all its
      // groups, attendance per group); any other lesson — its own page.
      to={lesson.parallel_session ? `/app/parallel-lessons/${lesson.parallel_session}` : `/app/lessons/${lesson.id}`}
      className={cn(
        'block rounded-lg border border-border bg-surface transition-colors hover:border-brand-200 hover:bg-brand-50/40',
        lesson.status === 'cancelled' && 'opacity-70',
        compact ? 'p-2.5' : 'p-4',
        className,
      )}
    >
      <p className={cn('font-mono font-semibold text-ink', compact ? 'text-xs' : 'text-sm')}>
        {formatTimeRange(lesson.start_time, lesson.end_time)}
      </p>
      <p className={cn('mt-1 font-medium text-ink', compact ? 'text-xs' : 'text-sm')}>
        {lesson.subject_name ?? 'Без предмета'}
        {!compact && lesson.topic ? <span className="font-normal text-ink-secondary"> — {lesson.topic}</span> : null}
      </p>
      <p className="mt-1 flex items-center gap-1 text-xs text-ink-secondary">
        {lesson.parallel_session ? <Layers className="size-3.5 shrink-0" aria-label="Параллельное занятие" /> : null}
        {lesson.group_name}
      </p>
      {lesson.room_name ? <p className="text-xs text-ink-muted">Аудитория: {lesson.room_name}</p> : null}
      {!compact ? (
        <div className="mt-2">
          <Badge tone={LESSON_STATUS_TONE[lesson.status]}>{lesson.status_display}</Badge>
        </div>
      ) : null}
    </Link>
  )
}
