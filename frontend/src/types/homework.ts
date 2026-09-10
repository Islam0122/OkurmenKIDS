export type HomeworkResultStatus = 'not_submitted' | 'submitted' | 'checked' | 'late'

export const HOMEWORK_RESULT_STATUS_LABELS: Record<HomeworkResultStatus, string> = {
  not_submitted: 'Не сдано',
  submitted: 'Сдано',
  checked: 'Проверено',
  late: 'Сдано с опозданием',
}

/** `apps.academy.serializers.HomeworkSerializer` — the assignment, not a student's result. */
export interface Homework {
  id: number
  lesson: number
  group_name: string
  lesson_date: string
  title: string
  description: string
  deadline: string | null
  results_count: number
  created_at: string
  updated_at: string
}

/**
 * `apps.academy.serializers.HomeworkResultSerializer`.
 *
 * The grading roster endpoint (`GET /homeworks/:id/results/`) returns one row
 * per active student, including a `not_submitted` placeholder (with `id`,
 * `submitted_at`/`checked_at`/`created_at`/`updated_at` all `null`) for
 * students with no HomeworkResult row yet.
 */
export interface HomeworkResult {
  id: number | null
  homework: number
  homework_title: string
  student: number
  student_name: string
  status: HomeworkResultStatus
  status_display: string
  score: number | null
  comment: string
  submitted_at: string | null
  checked_at: string | null
  created_at: string | null
  updated_at: string | null
}

/** Body item for `POST /homeworks/:id/results/` (bulk grading). `score` is 0-10. */
export interface BulkHomeworkResultItem {
  student: number
  status: HomeworkResultStatus
  score?: number | null
  comment?: string
}
