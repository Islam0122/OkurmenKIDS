import { Link } from 'react-router-dom'

import { Badge } from '@/components/ui/Badge'
import type { BadgeTone } from '@/components/ui/Badge'
import type { Lesson } from '@/types/academy'
import { cn } from '@/utils/cn'
import { formatTimeRange } from '@/utils/format'

const STATUS_TONE: Record<Lesson['status'], BadgeTone> = {
  planned: 'muted',
  completed: 'success',
  cancelled: 'danger',
}

export interface LessonCardProps {
  lesson: Lesson
  compact?: boolean
  className?: string
}

export function LessonCard({ lesson, compact = false, className }: LessonCardProps) {
  return (
    <Link
      to={`/app/lessons/${lesson.id}`}
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
      <p className="mt-1 text-xs text-ink-secondary">{lesson.group_name}</p>
      {lesson.room_name ? <p className="text-xs text-ink-muted">Аудитория: {lesson.room_name}</p> : null}
      {!compact ? (
        <div className="mt-2">
          <Badge tone={STATUS_TONE[lesson.status]}>{lesson.status_display}</Badge>
        </div>
      ) : null}
    </Link>
  )
}
