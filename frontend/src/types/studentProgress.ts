import type { KPIPeriodKey } from '@/types/kpi'

/** `GET /groups/{id}/student-progress/` — «Прогресс студентов» of the group
 * KPI (backend: services.analytics.student_progress). A rate / average is
 * `null` when there is nothing to measure («Нет данных»), never a fake 0. */

export interface StudentProgressCompared {
  attendance_rate: number | null
  homework_rate: number | null
  /** Homework score, 0–10. */
  average_score: number | null
  /** Test result, 0–100 %. */
  test_average: number | null
}

export interface StudentProgressRow extends StudentProgressCompared {
  id: number
  name: string
  first_name: string
  last_name: string
  status: string
  status_display: string
  in_group_now: boolean
  lessons_held: number
  attendance_marked: number
  attended: number
  late: number
  /** Absent + excused. */
  absences: number
  excused: number
  homework_due: number
  homework_done: number
  scored_count: number
  tests_count: number
  /** The previous comparable period, `null` when the student had nothing there. */
  previous: StudentProgressCompared | null
  /** Current − previous (percentage points / score points), `null` when either side is missing. */
  change: StudentProgressCompared
}

export interface StudentProgressPeriod {
  period: { key: KPIPeriodKey; start_date: string; end_date: string }
  comparison: { start_date: string; end_date: string }
}

export interface GroupStudentProgress extends StudentProgressPeriod {
  lessons_held: number
  students: StudentProgressRow[]
}

export interface StudentProgressLesson {
  id: number
  date: string
  lesson_number: number
  topic: string
  subject: string | null
  attendance: 'present' | 'absent' | 'late' | 'excused' | null
  attendance_display: string | null
  homework: { id: number; title: string; status: string | null; status_display: string; score: number | null }[]
}

export interface StudentProgressTest {
  id: string
  title: string
  date: string | null
  score: number
  passed: boolean | null
}

export interface StudentProgressDetail extends StudentProgressPeriod {
  student: StudentProgressRow
  lessons: StudentProgressLesson[]
  tests: StudentProgressTest[]
}

export interface StudentProgressParams {
  period: KPIPeriodKey
  start_date?: string
  end_date?: string
}
