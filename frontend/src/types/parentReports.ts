/** «Отчёты для родителей» (backend: apps.reports). Every number is computed
 * on the server from LMS records; a rate / average is `null` when there is
 * nothing to measure («Нет данных»), never a fake 0. */

export type ReportPeriodKey = 'today' | 'last_7_days' | 'this_week' | 'last_week' | 'this_month' | 'last_month' | 'custom'
export type ParentReportType = 'group' | 'students'
export type ParentReportLanguage = 'ru' | 'ky'
export type ParentReportFormat = 'png' | 'text' | 'both'
export type ParentReportStatus = 'ready' | 'partial' | 'failed'
export type StudentReportStatus = 'excellent' | 'good' | 'attention' | 'support' | 'no_data'
export type ComparisonTrend = 'up' | 'down' | 'stable' | 'no_data'

export interface ParentReportOptions {
  include_table: boolean
  include_group_stats: boolean
  include_recommendations: boolean
  include_comparison: boolean
}

export interface ParentReportConfig extends ParentReportOptions {
  period: ReportPeriodKey
  start_date?: string
  end_date?: string
  report_type: ParentReportType
  language: ParentReportLanguage
  output_format: ParentReportFormat
  student_ids?: number[]
}

export type ComparedMetric = 'attendance_rate' | 'homework_rate' | 'average_score' | 'test_average'

export interface ComparisonItem {
  current: number | null
  previous: number | null
  change: number | null
  trend: ComparisonTrend
}

export type Comparison = Record<ComparedMetric, ComparisonItem>

export interface ReportTest {
  title: string
  date: string | null
  score: number
  passed: boolean | null
}

export interface ReportStudent {
  id: number
  name: string
  first_name: string
  last_name: string
  lessons_held: number
  attendance_marked: number
  attended: number
  absences: number
  attendance_rate: number | null
  homework_due: number
  homework_done: number
  homework_rate: number | null
  /** Homework score 0–10. */
  average_score: number | null
  scored_count: number
  tests_count: number
  /** 0–100 %. */
  test_average: number | null
  tests: ReportTest[]
  status: StudentReportStatus
  previous: Record<ComparedMetric, number | null> | null
  comparison: Comparison
}

export interface ReportGroupStats {
  active_students: number
  planned_lessons: number
  conducted_lessons: number
  cancelled_lessons: number
  attendance_rate: number | null
  attended: number
  attendance_marked: number
  absences: number
  homework_rate: number | null
  homework_done: number
  homework_due: number
  average_score: number | null
  scored_count: number
  test_average: number | null
  tests_count: number
  excellent_count: number
  attention_count: number
  status_counts: Record<StudentReportStatus, number>
}

export interface ReportSnapshot {
  version: number
  generated_at: string
  today: string
  group: { id: number; name: string; course: string; trainers: string[] }
  teacher_scope_id: number | null
  period: { key: ReportPeriodKey; start: string; end: string; monthly: boolean }
  comparison_period: { start: string; end: string }
  group_stats: ReportGroupStats
  previous_group_stats: Record<ComparedMetric, number | null> | null
  group_comparison: Comparison
  students: ReportStudent[]
}

export interface RecommendationItem {
  key: string
  text: string
}

export type RecommendationSection = 'strengths' | 'attention' | 'parents'
export type RecommendationSections = Record<RecommendationSection, RecommendationItem[]>

export interface ReportRecommendations {
  group: RecommendationSections
  students: Record<string, RecommendationSections>
}

export interface ParentReportPreview {
  snapshot: ReportSnapshot
  text: string
  student_texts: Record<string, string>
  recommendations: ReportRecommendations
}

export interface ParentReportImage {
  id: number
  page: number
  student: number | null
  student_name: string
  width: number
  height: number
}

export interface ParentReportListItem {
  id: number
  group: number | null
  group_name: string
  course_name: string
  report_type: ParentReportType
  report_type_display: string
  language: ParentReportLanguage
  language_display: string
  output_format: ParentReportFormat
  output_format_display: string
  period_key: ReportPeriodKey
  start_date: string
  end_date: string
  compare_start_date: string | null
  compare_end_date: string | null
  status: ParentReportStatus
  status_display: string
  error: string
  final_text: string
  images: ParentReportImage[]
  students_count: number
  created_by_name: string
  created_at: string
  regenerated_from: number | null
}

export interface ParentReportDetail extends ParentReportListItem {
  options: ParentReportOptions & { student_ids: number[] | null }
  text: string
  edited_text: string
  student_texts: Record<string, string>
  edited_student_texts: Record<string, string>
  snapshot: ReportSnapshot
  recommendations: ReportRecommendations
}

export interface ParentReportTextUpdate {
  text?: string
  student_id?: number
  language?: ParentReportLanguage
  reset?: boolean
}
