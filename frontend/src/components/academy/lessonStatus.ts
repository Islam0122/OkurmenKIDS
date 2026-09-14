import type { BadgeTone } from '@/components/ui/Badge'
import type { LessonStatus } from '@/types/academy'

/**
 * The one shared status → label/tone mapping for `Lesson.status` — every
 * page that shows a lesson (dashboard, My Lessons, lesson cards, group
 * schedule, lesson detail) reads from here instead of keeping its own copy,
 * so a status never reads or colors differently in two different places.
 */
export const LESSON_STATUS_LABEL: Record<LessonStatus, string> = {
  scheduled: 'Запланировано',
  in_progress: 'Идёт занятие',
  completed: 'Проведено',
  cancelled: 'Отменено',
}

export const LESSON_STATUS_TONE: Record<LessonStatus, BadgeTone> = {
  scheduled: 'muted',
  in_progress: 'warning',
  completed: 'success',
  cancelled: 'danger',
}

export const LESSON_STATUS_OPTIONS: { value: LessonStatus; label: string }[] = (
  Object.keys(LESSON_STATUS_LABEL) as LessonStatus[]
).map((value) => ({ value, label: LESSON_STATUS_LABEL[value] }))
