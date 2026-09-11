/**
 * `apps.academy.serializers.AnalyticsDashboardSerializer` — everything here
 * is computed on demand by `apps.academy.services.analytics.get_dashboard`
 * from Lesson/Attendance/Homework/HomeworkResult/Student/Group/Teacher on
 * every request. There is no stored KPI record to go stale, and every
 * comparable number is `ComparisonMetric`-shaped — never compute
 * `change_percent` on the frontend, the backend is authoritative.
 */

export type KPIPeriodKey =
  | 'today'
  | 'yesterday'
  | 'last_7_days'
  | 'this_week'
  | 'last_week'
  | 'this_month'
  | 'last_month'
  | 'custom'

export type KPICompareMode = 'previous_period' | 'previous_month' | 'previous_week' | 'custom'

export type MetricTrend = 'up' | 'down' | 'stable'

/** `{value, previous_value, change, change_percent, trend}` — see
 * `services.analytics.metrics.build_metric`. `previous_value`/`change`/
 * `change_percent` are null whenever no comparison period was requested. */
export interface ComparisonMetric {
  value: number
  previous_value: number | null
  change: number | null
  change_percent: number | null
  trend: MetricTrend
}

export interface AnalyticsPeriod {
  key: KPIPeriodKey
  start_date: string
  end_date: string
}

export interface AnalyticsComparison {
  key: KPICompareMode
  start_date: string
  end_date: string
}

export interface AnalyticsFilters {
  teacher_id: number | null
  group_id: number | null
  course_id: number | null
  subject_id: number | null
}

export interface AnalyticsStudentsSection {
  total_students: ComparisonMetric
  active_students: ComparisonMetric
  inactive_students: ComparisonMetric
  new_students: ComparisonMetric
  students_left: ComparisonMetric
  average_students_per_group: ComparisonMetric
  groups_with_free_capacity: ComparisonMetric
  groups_at_capacity: ComparisonMetric
}

export interface TeacherWorkloadRow {
  teacher_id: number
  teacher_name: string
  lessons: number
}

export interface AnalyticsTeachersSection {
  total_teachers: ComparisonMetric
  active_teachers: ComparisonMetric
  teachers_with_lessons: ComparisonMetric
  teachers_without_lessons: ComparisonMetric
  average_lessons_per_teacher: ComparisonMetric
  teacher_workload: TeacherWorkloadRow[]
}

export interface AnalyticsGroupsSection {
  total_groups: ComparisonMetric
  active_groups: ComparisonMetric
  paused_groups: ComparisonMetric
  completed_groups: ComparisonMetric
  cancelled_groups: ComparisonMetric
  average_students_per_group: ComparisonMetric
  groups_near_capacity: ComparisonMetric
}

export interface LessonsByTeacherRow {
  teacher_id: number
  teacher_name: string
  lessons: number
}

export interface LessonsBySubjectRow {
  subject_id: number
  subject_name: string
  lessons: number
}

export interface AnalyticsLessonsSection {
  lessons_today: ComparisonMetric
  lessons_scheduled: ComparisonMetric
  lessons_completed: ComparisonMetric
  lessons_cancelled: ComparisonMetric
  lesson_completion_rate: ComparisonMetric
  lessons_by_teacher: LessonsByTeacherRow[]
  lessons_by_subject: LessonsBySubjectRow[]
}

export interface AnalyticsTrendPoint {
  date: string
  percent: number
}

export interface AnalyticsAttendanceSection {
  attendance_rate: ComparisonMetric
  present_count: ComparisonMetric
  absent_count: ComparisonMetric
  late_count: ComparisonMetric
  excused_count: ComparisonMetric
  students_with_repeated_absences: ComparisonMetric
  attendance_trend: AnalyticsTrendPoint[]
}

export interface AnalyticsHomeworkSection {
  homework_count: ComparisonMetric
  submitted_count: ComparisonMetric
  not_submitted_count: ComparisonMetric
  checked_count: ComparisonMetric
  late_count: ComparisonMetric
  submission_rate: ComparisonMetric
  average_score: ComparisonMetric
  homework_completion_trend: AnalyticsTrendPoint[]
}

export interface AnalyticsHealthComponents {
  attendance: number
  homework: number
  lesson_completion: number
  retention: number
  teacher_workload: number
}

export type AnalyticsHealthLevel = 'excellent' | 'good' | 'fair' | 'poor'

/** Computed fresh on every call — never persisted (see services.analytics.health). */
export interface AnalyticsHealth {
  score: number
  level: AnalyticsHealthLevel
  components: AnalyticsHealthComponents
}

export type InsightType = 'warning' | 'critical' | 'info'
export type InsightSeverity = 'low' | 'medium' | 'high'

export interface AnalyticsInsight {
  type: InsightType
  title: string
  message: string
  metric: string
  severity: InsightSeverity
}

/** Full response of `GET /academy/analytics/dashboard/`. */
export interface AnalyticsDashboard {
  period: AnalyticsPeriod
  comparison: AnalyticsComparison | null
  filters: AnalyticsFilters
  health: AnalyticsHealth
  students: AnalyticsStudentsSection
  teachers: AnalyticsTeachersSection
  groups: AnalyticsGroupsSection
  lessons: AnalyticsLessonsSection
  attendance: AnalyticsAttendanceSection
  homework: AnalyticsHomeworkSection
  insights: AnalyticsInsight[]
}
