/**
 * `/api/v1/control/` — "did the responsible trainer fill in everything their
 * lessons require?" Every count, percent, level and status here is computed
 * by the backend (apps.academy.services.control); the page only displays it.
 */

export type ControlStatus = 'ok' | 'attention' | 'not_filled' | 'no_data' | 'upcoming' | 'cancelled'

/** One cell's colour: every required record present / small gap / mostly unfilled / nothing required. */
export type ControlLevel = 'ok' | 'warning' | 'danger' | 'none'

export type ControlLessonState = 'due' | 'upcoming' | 'cancelled'

export type ControlPeriodKey = 'today' | 'this_week' | 'this_month' | 'last_month' | 'this_quarter' | 'custom'

export interface ControlRef {
  id: number
  name: string
}

export interface ControlTeacherRef extends ControlRef {
  is_active: boolean
}

export interface ControlComponent {
  completed: number
  total: number
  percent: number | null
  level: ControlLevel
}

export interface ControlRow {
  key: string
  /** The responsible trainer (`Lesson.effective_teacher`) — null for lessons nobody is assigned to. */
  teacher: ControlTeacherRef | null
  group: ControlRef
  subjects: ControlRef[]
  lessons: ControlComponent & { not_closed: number; upcoming: number; cancelled: number }
  attendance: ControlComponent
  homework: ControlComponent
  grades: ControlComponent & { students_missing: number }
  status: ControlStatus
  status_label: string
  problem_lessons: number
  issues: string[]
  first_problem_lesson_id: number | null
  last_activity_at: string | null
}

export interface ControlSummary {
  total_lessons: number
  completed_lessons: number
  not_closed_lessons: number
  upcoming_lessons: number
  cancelled_lessons: number
  attendance_completion: number | null
  homework_completion: number | null
  grade_completion: number | null
  students_without_grade: number
  attention_count: number
  problem_lessons: number
  rows_total: number
  status_counts: Record<Exclude<ControlStatus, 'cancelled'>, number>
}

export interface ControlFilters {
  period: ControlPeriodKey
  period_label: string
  start_date: string
  end_date: string
  program: number | null
  group: number | null
  teacher: number | null
  subject: number | null
  status: ControlStatus | null
}

export interface ControlOptions {
  periods: { key: ControlPeriodKey; label: string }[]
  teachers: ControlRef[]
  groups: ControlRef[]
  subjects: ControlRef[]
  statuses: { key: ControlStatus; label: string }[]
}

export interface ControlOverview {
  filters: ControlFilters
  summary: ControlSummary
  items: ControlRow[]
  options: ControlOptions
}

export type ControlComponentState =
  | 'ok'
  | 'missing'
  | 'partial'
  | 'unchecked'
  | 'waiting'
  | 'not_required'
  | 'no_students'
  | 'no_homework'

export interface ControlLesson {
  id: number
  lesson_number: number
  date: string
  start_time: string
  end_time: string
  topic: string
  subject: ControlRef | null
  group: ControlRef
  teacher: ControlTeacherRef | null
  /** Set when a substitute gave the lesson instead of the program's own trainer. */
  planned_teacher: ControlTeacherRef | null
  state: ControlLessonState
  lesson_status: 'scheduled' | 'in_progress' | 'completed' | 'cancelled'
  lesson_status_label: string
  closed: boolean
  closed_at: string | null
  closed_by: ControlRef | null
  status: ControlStatus
  status_label: string
  students_total: number
  attendance: { state: ControlComponentState; marked: number; total: number; missing_students: ControlRef[] }
  homework: {
    state: ControlComponentState
    id: number | null
    given: boolean
    not_required: boolean
    deadline: string | null
    pending_check: number
  }
  grades: { state: ControlComponentState; given: number; total: number; missing: number; missing_students: ControlRef[] }
  problems: string[]
  notes: string[]
  last_activity_at: string | null
}

export interface ControlDetail {
  filters: ControlFilters
  row: ControlRow
  lessons: ControlLesson[]
}
