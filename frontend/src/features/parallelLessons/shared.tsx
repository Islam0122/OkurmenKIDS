import { format, parseISO } from 'date-fns'
import { ru } from 'date-fns/locale'
import { useLocation } from 'react-router-dom'

import { Badge } from '@/components/ui/Badge'
import type { BadgeTone } from '@/components/ui/Badge'
import type { SessionStatus } from '@/types/parallelLessons'

/** The section lives in two workspaces: /app (Admin, Team Lead, Trainer)
 * and /assistant (Assistant, Admin). Links stay inside the current one. */
export function useParallelBase(): string {
  const { pathname } = useLocation()
  return pathname.startsWith('/assistant') ? '/assistant/parallel-lessons' : '/app/parallel-lessons'
}

const STATUS_TONE: Record<SessionStatus, BadgeTone> = {
  scheduled: 'info',
  in_progress: 'warning',
  completed: 'success',
  cancelled: 'muted',
}

export function SessionStatusBadge({ status, label }: { status: SessionStatus; label: string }) {
  return <Badge tone={STATUS_TONE[status]}>{label}</Badge>
}

export const hm = (value: string) => value.slice(0, 5)

export function formatDay(value: string, pattern = 'd MMMM, EEEE') {
  return format(parseISO(value), pattern, { locale: ru })
}

export const MARK_LABELS = {
  present: 'Присутствовал',
  late: 'Опоздал',
  absent: 'Отсутствовал',
  excused: 'Уваж. причина',
} as const
