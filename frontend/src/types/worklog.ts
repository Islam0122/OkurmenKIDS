/** Team Lead «Рабочий журнал»: journal records, tasks and reports (backend: apps.worklog). */

export type EntryKind = 'log' | 'task'

export type WorkType =
  | 'lesson_control'
  | 'trainer'
  | 'student'
  | 'exam'
  | 'hackathon'
  | 'meeting'
  | 'internship'
  | 'probation'
  | 'analytics'
  | 'problem'
  | 'other'

export type TaskStatus = 'new' | 'in_progress' | 'done' | 'overdue' | 'postponed' | 'escalated'
export type Priority = 'low' | 'medium' | 'high' | 'critical'

export type ReportKind =
  | 'daily'
  | 'weekly'
  | 'meeting'
  | 'lesson_visit'
  | 'trainer_review'
  | 'problem_student'
  | 'internship'
  | 'probation'
  | 'monthly'

export interface Ref {
  id: number
  name: string
}

export interface Choice<T extends string = string> {
  value: T
  label: string
}

export interface WorkLogEntry {
  id: number
  entry_kind: EntryKind
  date: string
  time_from: string | null
  time_to: string | null
  work_type: WorkType
  group: number | null
  teacher: number | null
  student: number | null
  with_whom: string
  title: string
  goal: string
  description: string
  result: string
  problem: string
  decision: string
  next_action: string
  responsible: string
  deadline: string | null
  priority: Priority
  status: TaskStatus
  comment: string
  report: number | null
  created_at: string
  updated_at: string
  author: Ref
  group_detail: Ref | null
  teacher_detail: Ref | null
  student_detail: Ref | null
  work_type_label: string
  priority_label: string
  /** «Просрочено» is computed: an open record past its deadline. */
  effective_status: TaskStatus
  effective_status_label: string
  is_overdue: boolean
  /** Section 6.13 sentence: когда, что, с кем, результат, что дальше. */
  summary: string
  can_edit: boolean
}

export type WorkLogEntryInput = Partial<
  Omit<
    WorkLogEntry,
    | 'id'
    | 'created_at'
    | 'updated_at'
    | 'author'
    | 'group_detail'
    | 'teacher_detail'
    | 'student_detail'
    | 'work_type_label'
    | 'priority_label'
    | 'effective_status'
    | 'effective_status_label'
    | 'is_overdue'
    | 'summary'
    | 'can_edit'
  >
>

export interface WorkLogSummary {
  today: number
  open: number
  overdue: number
  due_today: number
}

export type FieldType =
  | 'text'
  | 'textarea'
  | 'list'
  | 'date'
  | 'number'
  | 'percent'
  | 'score'
  | 'select'
  | 'multiselect'
  | 'rows'

export interface SchemaColumn {
  key: string
  label: string
  type: FieldType
}

export interface SchemaField {
  key: string
  label: string
  type: FieldType
  required?: boolean
  help?: string
  placeholder?: string
  options?: string[]
  columns?: SchemaColumn[]
}

export type ReportLink = 'group' | 'teacher' | 'student' | 'lesson'

export interface ReportKindSchema {
  kind: ReportKind
  label: string
  period: 'date' | 'range'
  links: ReportLink[]
  required_links: ReportLink[]
  description: string
  statuses: Choice[]
  fields: SchemaField[]
}

export interface WorklogOptions {
  report_kinds: ReportKindSchema[]
  work_types: Choice<WorkType>[]
  statuses: Choice<TaskStatus>[]
  priorities: Choice<Priority>[]
  groups: { id: number; name: string; status: string }[]
  teachers: { id: number; name: string; is_active: boolean }[]
  students: { id: number; name: string; group: number | null }[]
}

export type ReportValue = string | number | string[] | Record<string, string>[]
export type ReportData = Record<string, ReportValue>

/** LMS figures, snapshot at the time of writing (apps.worklog.metrics). */
export type ReportMetrics = Record<string, unknown>

export interface TeamLeadReport {
  id: number
  kind: ReportKind
  kind_label: string
  date: string
  period_start: string | null
  period_end: string | null
  group: number | null
  teacher: number | null
  student: number | null
  lesson: number | null
  data: ReportData
  metrics: ReportMetrics
  metrics_calculated_at: string | null
  status: string
  status_label: string
  title: string
  author: Ref
  group_detail: Ref | null
  teacher_detail: Ref | null
  student_detail: Ref | null
  can_edit: boolean
  created_at: string
  updated_at: string
  /** Detail only: tasks linked to the report (meeting decisions). */
  tasks?: WorkLogEntry[]
  /** Detail only, daily report: the author's journal records of the day. */
  day_entries?: WorkLogEntry[]
}

export interface TeamLeadReportInput {
  kind?: ReportKind
  date?: string
  period_start?: string | null
  period_end?: string | null
  group?: number | null
  teacher?: number | null
  student?: number | null
  lesson?: number | null
  data?: ReportData
  status?: string
}
