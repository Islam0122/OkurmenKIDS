/** /api/v1/monitoring/* — shapes returned by the backend (apps.testing.monitoring_api). */

export type AttemptStatus = 'in_progress' | 'completed' | 'expired' | 'terminated'
export type Severity = 'normal' | 'warning' | 'critical'
export type AttemptMode = 'exam' | 'training'

export interface MonitoringOverview {
  active_exams: number
  active_trainers: number
  active_students: number
  completed: number
  passed: number
  failed: number
  expired: number
  terminated: number
  violations: number
  flagged_attempts: number
  average_score: number | null
}

export interface MonitoringAttempt {
  id: string
  student_name: string
  student_id: number | null
  group: { id: number; name: string } | null
  teacher: { id: number; name: string } | null
  session: { id: string; title: string }
  test: { id: string; title: string; subject: string }
  mode: AttemptMode
  exam_mode: boolean
  started_at: string
  finished_at: string | null
  expires_at: string | null
  remaining_seconds: number | null
  duration_seconds: number | null
  answered: number
  question_total: number
  status: AttemptStatus
  score: number | null
  passed: boolean | null
  passing_score: number
  tab_switch_count: number
  fullscreen_exits: number
  violation_count: number
  max_tab_switches: number | null
  severity: Severity
  finish_reason: string
  subject?: { id: number; name: string } | null
  /** results only (monitoring/results/, attempts/:id) */
  correct_count?: number
  incorrect_count?: number
  attempt_no?: number
}

export interface MonitoringEvent {
  id: number
  type: string
  label: string
  severity: 'danger' | 'warning' | 'info'
  timestamp: string
  question: number | null
  detail: string
}

export interface MonitoringAttemptDetail extends MonitoringAttempt {
  events: MonitoringEvent[]
  violations: Record<string, number>
  questions: {
    number: number
    question_id: string
    text?: string
    status: string
    /** finished attempts: the student's answer and the correct one */
    full_text?: string
    type?: string
    selected?: string[]
    correct?: string[]
    answer_text?: string
    answered_at?: string | null
  }[]
}

export interface StatRow {
  attempts: number
  students: number
  active: number
  completed: number
  passed: number
  pass_rate: number | null
  average_score: number | null
  violations: number
  avg_duration_seconds: number | null
}

export interface TeacherPerformance extends StatRow {
  teacher: { id: number; name: string }
}

export interface GroupStats extends StatRow {
  group: { id: number; name: string }
}

export interface GroupDetail extends StatRow {
  group: { id: number; name: string }
  active_exams: number
  failed_students: string[]
  students_list: (StatRow & { student_name: string; failed: number })[]
}

export interface TrainerStats extends StatRow {
  session: { id: string; title: string }
  test: { id: string; title: string; subject: string }
  mode: AttemptMode
  is_public: boolean
}

export interface DifficultQuestion {
  number: number
  question_id: string
  text: string
  answered: number
  correct: number
  incorrect: number
  correct_rate: number
  incorrect_rate: number
}

export interface TrainerDetail {
  session: { id: string; title: string }
  stats: TrainerStats | null
  difficult_questions: DifficultQuestion[]
}

export interface MonitoringFilterOptions {
  groups: { id: number; name: string }[]
  subjects: { id: number; name: string }[]
  teachers: { id: number; name: string }[]
  sessions: { id: string; title: string; mode: AttemptMode }[]
  team_view: boolean
}

export interface MonitoringFilters {
  q?: string
  student?: string
  test?: string
  result?: string
  score_min?: string
  score_max?: string
  page_size?: number
  group?: string
  teacher?: string
  subject?: string
  session?: string
  mode?: string
  status?: string
  date_from?: string
  date_to?: string
  violations?: string
  page?: number
}

/** /monitoring/results/summary/ — services.results.overview + dynamics */
export interface ResultsSummary {
  attempts: number
  students_tested: number
  groups: number
  tests: number
  passed: number
  failed: number
  pass_rate: number | null
  failed_rate: number | null
  average_score: number | null
  best_score: number | null
  lowest_score: number | null
  average_correct: number | null
  average_questions: number | null
  best_student: { id: number; name: string; average_score: number | null; attempts: number } | null
  best_group: { id: number; name: string; average_score: number | null; attempts: number } | null
  dynamics: { date: string; average_score: number | null; attempts: number; pass_rate: number | null }[]
  /** only with a `group` filter: active students of the group */
  students_total?: number
}

export interface StudentResultRow {
  student: { id: number; name: string }
  attempts: number
  average_score: number | null
  best_score: number | null
  last_score: number | null
  last_passed: boolean | null
  last_at: string | null
}

export interface ResultBreakdownRow {
  id: string
  name: string
  attempts: number
  students: number
  average_score: number | null
  pass_rate: number | null
}

export type ResultBreakdownBy = 'group' | 'subject' | 'teacher' | 'test'
