import type { GroupStatus } from '@/types/academy'

/** `apps.academy.serializers.AcademyMonthlyReportStatsSerializer` — computed
 * fresh on every request by
 * `services.academy_monthly_report.compute_academy_monthly_stats`, never
 * stored. A `null` field means the current data genuinely can't answer that
 * question (e.g. no reschedule status on Lesson) — render "Нет данных",
 * never fabricate a number. */
export interface AcademyReportPeriod {
  year: number
  month: number
  start_date: string
  end_date: string
}

export interface AcademyReportAttendance {
  total: number
  present: number
  late: number
  absent: number
  excused: number
  rate: number
}

export interface AcademyReportStudents {
  active: number
  new: number
  left: number
  completed: number
  paused: number
}

export interface AcademyReportGroupRow {
  id: number
  name: string
  students_count: number
  lessons_count: number
  attendance_rate: number
  status: GroupStatus
  status_display: string
}

export interface AcademyReportTeacherRow {
  id: number
  name: string
  lessons_completed: number
  students_count: number
  attendance_rate: number
  kpi_total: number | null
}

export interface AcademyReportLessons {
  scheduled: number
  completed: number
  cancelled: number
  rescheduled: number | null
  attendance_rate: number
}

export interface AcademyReportHomework {
  assigned: number
  checked: number
  pending_review: number
  checked_rate: number | null
}

export interface AcademyReportWeekPoint {
  label: string
  percent: number
}

export interface AcademyReportKPI {
  attendance: number
  homework: number
  lessons: number
  student_progress: number | null
  total: number
}

export interface AcademyReportReasonBreakdownRow {
  reason: string
  reason_display: string
  count: number
  percent: number
}

/** `{count, supported}` — always render `count`; `supported` distinguishes
 * "0 real events this period" from a genuinely unimplemented metric,
 * though every field below is `supported: true` today. */
export interface AcademyReportEducationStatusMetric {
  count: number
  supported: boolean
}

export interface AcademyReportMovement {
  left: number
  completed: AcademyReportEducationStatusMetric
  paused: AcademyReportEducationStatusMetric
  continued: AcademyReportEducationStatusMetric
  /** Distinct from reactivation-after-withdrawal: this reads only
   * `CONTINUED` events (ending a pause), never `REACTIVATED` ones. */
  returned_after_pause: AcademyReportEducationStatusMetric
  /** Always a real (possibly empty) list — empty means no departures were
   * recorded this period, not "unsupported". */
  reasons: AcademyReportReasonBreakdownRow[]
}

export interface AcademyReportAttentionItem {
  type: string
  message: string
}

export interface AcademyReportStats {
  period: AcademyReportPeriod
  /** False when the academy had no lessons/groups this month — the signal
   * to show "Нет данных за этот месяц" instead of a wall of zeros. */
  has_data: boolean
  students_count: number
  groups_count: number
  teachers_count: number
  lessons_completed: number
  attendance: AcademyReportAttendance
  students: AcademyReportStudents
  groups: AcademyReportGroupRow[]
  teachers: AcademyReportTeacherRow[]
  lessons: AcademyReportLessons
  homework: AcademyReportHomework
  weekly_dynamics: AcademyReportWeekPoint[]
  kpi: AcademyReportKPI
  movement: AcademyReportMovement
  attention: AcademyReportAttentionItem[]
}

/** `apps.academy.serializers.AcademyMonthlyReportSerializer` */
export interface AcademyMonthlyReport {
  id: number
  year: number
  month: number
  comment: string
  stats: AcademyReportStats
  created_at: string
  updated_at: string
}

/** `POST /academy-reports/` response — 201 means a new report was created;
 * a 200 with `created: false` means one for this month already existed. */
export interface CreateAcademyReportResult {
  created: boolean
  report: AcademyMonthlyReport
}
