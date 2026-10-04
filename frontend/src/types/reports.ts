/** `/api/v1/reports/*` — the academy-wide Reports/KPI API (apps.academy.report_views,
 * services.reports). Admin and Team Lead only; every figure is computed. */

export type ReportPeriodKey = 'today' | 'this_week' | 'this_month' | 'last_month' | 'this_quarter' | 'custom'

/** services.kpi_engine.kpi_status */
export type KpiLevel = 'good' | 'attention' | 'low' | 'no_data'

export interface ReportParams {
  period: ReportPeriodKey
  start_date?: string
  end_date?: string
  program?: number
  group?: number
  teacher?: number
  subject?: number
  q?: string
  sort?: string
  page?: number
  page_size?: number
}

export interface ReportFiltersInfo {
  period: ReportPeriodKey
  period_label: string
  start_date: string
  end_date: string
}

export interface ReportPage<T> {
  filters?: ReportFiltersInfo
  count: number
  page: number
  pages: number
  page_size: number
  search: string
  sort: string
  results: T[]
}

interface Rates {
  attendance_rate: number | null
  homework_rate: number | null
  activity_rate: number | null
  progress_rate: number | null
  kpi: number | null
  kpi_level: KpiLevel
  has_data: boolean
}

export interface ReportTeacherRow extends Rates {
  id: number
  name: string
  position: string
  is_active: boolean
  groups: { id: number; name: string; kpi: number | null }[]
  groups_count: number
  subjects: string[]
  students: { total: number; active: number; left: number }
  lessons: { total: number; held: number }
}

export interface ReportGroupRow extends Rates {
  id: number
  name: string
  program: string
  status: string
  status_display: string
  start_date: string
  teachers: { id: number; name: string }[]
  teacher_names: string
  has_teacher: boolean
  subjects: string[]
  students: { total: number; active: number; left: number; new: number; returned: number }
  lessons: { total: number; held: number; cancelled?: number; due?: number }
}

export interface ReportSubjectRow extends Rates {
  id: number
  name: string
  is_active: boolean
  groups_count: number
  teachers_count: number
  teacher_names: string
  students: { total: number; active: number }
  average_score: number | null
  lessons: { total: number; held: number; due: number; cancelled: number }
}

export interface ReportStudentRow {
  id: number
  name: string
  group: string
  group_id: number | null
  status: string
  status_display: string
  is_active: boolean
  attendance_total: number
  attended: number
  attendance_rate: number | null
  homework_results: number
  homework_submitted: number
  homework_rate: number | null
  average_score: number | null
  progress_rate: number | null
  level: KpiLevel
}

export interface KpiContract {
  metrics: Record<string, number | null>
  kpi: {
    total: number | null
    status: KpiLevel
    status_label: string
    weights: { key: string; label: string; short: string; weight: number }[]
  }
}

export interface ReportLessonStats {
  lessons: { total: number; held: number; cancelled: number; due: number }
  attendance: { total: number; present: number; late: number; absent: number; excused: number; rate: number | null; absence_rate: number | null }
  homework: {
    assigned: number
    results: number
    submitted: number
    not_submitted: number
    checked: number
    late: number
    completion_rate: number | null
    average_score: number | null
  }
}

export interface ReportTeacherDetail extends ReportLessonStats, KpiContract {
  teacher: {
    id: number
    name: string
    position: string
    email: string
    phone: string
    is_active: boolean
    hire_date: string | null
  }
  filters: ReportFiltersInfo
  groups: { id: number; name: string; kpi: number | null }[]
  subjects: string[]
  students: { total: number; active: number; left: number }
  has_data: boolean
  group_performance: ReportGroupRow[]
}

export interface ReportGroupDetail extends ReportLessonStats, KpiContract {
  group: {
    id: number
    name: string
    program: string
    status_display: string
    teachers: { id: number; name: string }[]
    teacher_names: string
    subjects: string[]
  }
  filters: ReportFiltersInfo
  students: { total: number; active: number; left: number }
  has_data: boolean
  plan_progress: number | null
  teacher_breakdown: ({ id: number | null; name: string } & Rates & { lessons: { total: number; held: number } })[]
  students_list: ReportPage<ReportStudentRow>
}

export interface ReportOverview extends ReportLessonStats, KpiContract {
  filters: ReportFiltersInfo
  students: { total: number; active: number; left: number; new: number; retention_rate: number | null }
  teachers: { total: number; with_groups: number; without_groups: number }
  groups: { total: number; active: number; without_teacher: number }
  has_data: boolean
  top_groups: ReportGroupRow[]
  attention_groups: ReportGroupRow[]
}

export interface ReportFilterOptions {
  periods: { key: ReportPeriodKey; label: string }[]
  programs: { id: number; name: string }[]
  groups: { id: number; name: string }[]
  teachers: { id: number; name: string }[]
  subjects: { id: number; name: string }[]
}
