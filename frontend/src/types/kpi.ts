/**
 * `apps.academy.serializers.AnalyticsDashboardSerializer` — everything here
 * is computed on demand by `AnalyticsService` from Lesson/Attendance/
 * Homework/HomeworkResult on every request. There is no stored KPI record
 * to go stale: mark attendance, then re-fetch, and the numbers already
 * reflect it.
 */
import type { GroupStatus } from '@/types/academy'

export interface AnalyticsPeriod {
  start_date: string
  end_date: string
}

export interface AnalyticsFilters {
  teacher_id: number | null
  group_id: number | null
}

export interface AnalyticsOverview {
  groups: number
  teachers: number
  students: number
  lessons: number
  attendance_percent: number
  homework_completion_percent: number
  average_score: number
}

export interface AnalyticsLessonStats {
  total: number
  completed: number
  cancelled: number
  planned: number
  completion_rate: number
}

export interface AnalyticsTimeSeriesPoint {
  date: string
  percent: number
}

export interface AnalyticsAttendanceStats {
  total: number
  present: number
  absent: number
  late: number
  excused: number
  percent: number
  by_date: AnalyticsTimeSeriesPoint[]
}

export interface AnalyticsHomeworkStats {
  total_homeworks: number
  total_results: number
  submitted: number
  checked: number
  late: number
  not_submitted: number
  completed: number
  completion_percent: number
  average_score: number
  by_date: AnalyticsTimeSeriesPoint[]
}

export interface AnalyticsGroupRow {
  id: number
  name: string
  teacher: string
  students: number
  lessons: number
  completed_lessons: number
  cancelled_lessons: number
  planned_lessons: number
  attendance_percent: number
  homework_completion_percent: number
  average_score: number
  status: GroupStatus
  status_display: string
}

export interface AnalyticsTeacherRow {
  id: number
  name: string
  groups: number
  students: number
  lessons: number
  attendance_percent: number
  homework_completion_percent: number
  average_score: number
}

export interface AnalyticsStudentRow {
  id: number
  name: string
  group: string | null
  lessons: number
  attendance_percent: number
  homework_completion_percent: number
  average_score: number
}

export interface AnalyticsLessonsByStatusPoint {
  status: 'completed' | 'planned' | 'cancelled'
  label: string
  count: number
}

export interface AnalyticsGroupPerformancePoint {
  group: string
  attendance_percent: number
}

export interface AnalyticsTeacherPerformancePoint {
  teacher: string
  attendance_percent: number
}

export interface AnalyticsStudentsByGroupPoint {
  group: string
  students: number
}

export interface AnalyticsCharts {
  attendance_over_time: AnalyticsTimeSeriesPoint[]
  lessons_by_status: AnalyticsLessonsByStatusPoint[]
  students_by_group: AnalyticsStudentsByGroupPoint[]
  homework_completion_over_time: AnalyticsTimeSeriesPoint[]
  teacher_performance: AnalyticsTeacherPerformancePoint[]
  group_performance: AnalyticsGroupPerformancePoint[]
}

/** Full response of `GET /academy/analytics/dashboard/`. */
export interface AnalyticsDashboard {
  period: AnalyticsPeriod
  filters: AnalyticsFilters
  overview: AnalyticsOverview
  lessons: AnalyticsLessonStats
  attendance: AnalyticsAttendanceStats
  homework: AnalyticsHomeworkStats
  groups: AnalyticsGroupRow[]
  teachers: AnalyticsTeacherRow[]
  top_students: AnalyticsStudentRow[]
  charts: AnalyticsCharts
}
