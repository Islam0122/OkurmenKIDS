import type { Teacher } from '@/types/academy'

/** `apps.academy.serializers.MonthlyReportStatsSerializer` — computed fresh
 * on every request by `services.monthly_report.compute_monthly_stats`,
 * never stored. Never fabricate any of these on the frontend. */
export interface MonthlyReportPeriod {
  year: number
  month: number
  start_date: string
  end_date: string
}

export interface MonthlyReportAttendance {
  total: number
  present: number
  late: number
  absent: number
  excused: number
  rate: number
}

export interface MonthlyReportHomework {
  assigned: number
  checked: number
  submission_rate: number
  average_score: number | null
}

export interface MonthlyReportGroupRow {
  id: number
  name: string
  students_count: number
  lessons_count: number
}

export interface MonthlyReportWeekPoint {
  label: string
  percent: number
}

export interface MonthlyReportKPI {
  attendance: number
  homework: number
  lessons: number
  student_progress: number
  total: number
}

export interface MonthlyReportStats {
  period: MonthlyReportPeriod
  /** False when the teacher had no lessons and no groups this month — the
   * signal to show "Нет данных за этот месяц" instead of a wall of zeros. */
  has_data: boolean
  lessons_total: number
  lessons_completed: number
  students_count: number
  groups_count: number
  attendance: MonthlyReportAttendance
  homework: MonthlyReportHomework
  groups: MonthlyReportGroupRow[]
  weekly_dynamics: MonthlyReportWeekPoint[]
  kpi: MonthlyReportKPI
}

/** `apps.academy.serializers.MonthlyTeacherReportSerializer` */
export interface MonthlyTeacherReport {
  id: number
  teacher: Teacher
  year: number
  month: number
  comment: string
  stats: MonthlyReportStats
  created_at: string
  updated_at: string
}

/** `POST /monthly-reports/` response — 201 means a new report was created;
 * a 200 with `created: false` means one for this month already existed
 * (see api/monthlyReports.ts) and `report` is that existing one. */
export interface CreateMonthlyReportResult {
  created: boolean
  report: MonthlyTeacherReport
}
