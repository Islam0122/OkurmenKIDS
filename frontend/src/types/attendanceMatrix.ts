/** Monthly attendance & homework matrix — /api/v1/attendance-matrix/
 * (backend: apps.attendance_matrix). Attendance and homework stay two
 * separate values in every cell. */

export type CellCode = 'done' | 'partial' | 'excused' | 'absent' | 'empty' | 'planned' | 'no_lesson'
export type MatrixAttendance = 'present' | 'late' | 'excused' | 'absent'
export type MatrixHomework = 'done' | 'missed' | 'pending' | 'none'
export type MatrixPeriod = 'day' | 'week' | 'month'
export type WarningLevel = 'critical' | 'attention' | 'warning'
export type MatrixRole = 'admin' | 'teacher' | 'assistant' | 'team_lead' | 'operations_director'

export interface MatrixWarning {
  code: string
  level: WarningLevel
  label: string
}

export interface MatrixColumnStats {
  present: number
  excused: number
  absent: number
  unmarked: number
  hw_missed: number
  marked: number
  percent: number | null
}

export interface MatrixColumn {
  lesson_id: number
  date: string
  weekday: string
  start: string
  end: string
  lesson_number: number
  topic: string
  subject: string
  teacher: string
  teacher_id: number | null
  status: string
  held: boolean
  editable_day: boolean
  has_homework: boolean
  can_edit: boolean
  stats: MatrixColumnStats
}

export interface MatrixCell {
  lesson_id: number
  code: CellCode
  attendance: MatrixAttendance | null
  homework: MatrixHomework
  has_comment: boolean
}

export interface StudentStats {
  present: number
  late: number
  excused: number
  absent: number
  unmarked: number
  marked: number
  lessons: number
  percent: number | null
  hw_done: number
  hw_missed: number
  hw_due: number
  hw_percent: number | null
  done_cells: number
  consecutive_absences: number
}

export interface MatrixStudentRef {
  id: number
  name: string
  status: string
  status_display: string
  in_group: boolean
}

export interface MatrixRow {
  student: MatrixStudentRef
  cells: MatrixCell[]
  stats: StudentStats
  warnings: MatrixWarning[]
  level: WarningLevel | null
}

export interface CountPercent {
  count: number
  percent: number | null
}

export interface MatrixSummary {
  present: number
  late: number
  excused: number
  absent: number
  unmarked: number
  marked: number
  hw_done: number
  hw_missed: number
  hw_due: number
  done_cells: number
  lessons: number
  students: number
  percent: number | null
  hw_percent: number | null
  cards: { done: CountPercent; excused: CountPercent; absent: CountPercent; hw_missed: CountPercent }
  warnings: Record<WarningLevel, number>
  groups?: number
}

export interface RankingRow {
  place: number
  student: MatrixStudentRef
  percent: number | null
  present: number
  absent: number
  hw_percent: number | null
}

export interface MatrixCapabilities {
  role: MatrixRole | null
  can_edit: boolean
  can_comment: boolean
  can_view_history: boolean
  can_export: boolean
}

export interface MatrixPeriodInfo {
  kind: MatrixPeriod
  start: string
  end: string
  label: string
  prev: string
  next: string
}

export interface Thresholds {
  consecutive_absences_warning: number
  monthly_absences_attention: number
  monthly_absences_critical: number
  missed_homework_warning: number
}

export interface GroupMatrix {
  group: { id: number; name: string; status: string; status_display: string; course: string; students_count: number }
  period: MatrixPeriodInfo
  columns: MatrixColumn[]
  rows: MatrixRow[]
  summary: MatrixSummary
  ranking: RankingRow[]
  thresholds: Thresholds
  capabilities: MatrixCapabilities
  legend: { code: CellCode; label: string }[]
  filtered: boolean
  /** Every trainer of the period's lessons — options of the trainer filter. */
  trainers: { id: number; name: string }[]
}

export interface MatrixParams {
  period?: MatrixPeriod
  date?: string
  search?: string
  status?: CellCode | ''
  homework?: 'done' | 'missed' | ''
  level?: WarningLevel | ''
  teacher?: number
}

export interface UserRef {
  id: number
  name: string
  role: string
}

export interface CellHistoryEntry {
  id: number
  at: string
  actor: UserRef | null
  actor_role: string
  changes: { field: string; label: string; before: string; after: string }[]
}

export interface CellDetail {
  student: { id: number; name: string }
  group: { id: number; name: string }
  lesson: {
    id: number
    date: string
    start: string
    end: string
    topic: string
    number: number
    subject: string
    teacher: string
    status: string
    status_display: string
    held: boolean
  }
  attendance: MatrixAttendance | null
  excuse_reason: string
  comment: string
  homework: MatrixHomework
  homeworks: { id: number; title: string; deadline: string | null; status: string | null; status_display: string }[]
  homework_not_required: boolean
  updated_by: UserRef | null
  updated_at: string | null
  edit_level: 'full' | 'comment' | 'none'
  edit_reason: string
  history: CellHistoryEntry[]
}

export interface CellUpdate {
  lesson: number
  student: number
  attendance?: MatrixAttendance | null
  excuse_reason?: string
  comment?: string
  homework?: 'done' | 'missed'
}

export interface OverviewGroup {
  id: number
  name: string
  course: string
  status: string
  status_display: string
  trainers: string[]
  students: number
  lessons: number
  percent: number | null
  hw_percent: number | null
  present: number
  excused: number
  absent: number
  unmarked: number
  hw_missed: number
  warnings: Record<WarningLevel, number>
}

export interface OverviewTrainer {
  id: number
  name: string
  groups: string[]
  lessons: number
  present: number
  excused: number
  absent: number
  unmarked: number
  percent: number | null
  hw_percent: number | null
  fill_rate: number | null
}

export interface ProblemStudent {
  student: MatrixStudentRef
  group: { id: number; name: string }
  stats: StudentStats
  warnings: MatrixWarning[]
  level: WarningLevel
}

export interface Overview {
  period: MatrixPeriodInfo
  summary: MatrixSummary
  groups: OverviewGroup[]
  trainers: OverviewTrainer[]
  problem_students: ProblemStudent[]
  ranking: RankingRow[]
  trend: { year: number; month: number; label: string; percent: number | null; marked: number; absent: number }[]
  thresholds: Thresholds
  excused: ExcusedEntry[]
  assistants: AssistantActivity[]
  history: JournalEntry[]
}

export interface ExcusedEntry {
  id: number
  student: { id: number; name: string }
  group: { id: number; name: string }
  lesson_id: number
  date: string
  reason: string
  comment: string
  missing_reason: boolean
  updated_by: UserRef | null
}

export interface AssistantActivity {
  user: UserRef
  changes: number
  attendance_changes: number
  homework_changes: number
  comments: number
  students: number
  groups: string[]
  last_change: string | null
}

export interface JournalEntry extends CellHistoryEntry {
  student: { id: number; name: string }
  group: { id: number; name: string }
  lesson_id: number
  date: string
}

export interface OverviewParams {
  date?: string
  subject?: number
  teacher?: number
  group?: number
}

export interface MatrixMeta {
  role: MatrixRole | null
  groups: { id: number; name: string; status: string }[]
  subjects: { id: number; name: string }[]
  teachers: { id: number; name: string }[]
}

export interface MatrixSettings extends Thresholds {
  team_lead_can_edit: boolean
  operations_director_can_edit: boolean
  updated_at: string
  can_edit_thresholds: boolean
  can_edit_permissions: boolean
}
