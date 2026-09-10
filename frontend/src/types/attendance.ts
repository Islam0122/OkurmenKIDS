export type AttendanceStatus = 'present' | 'absent' | 'late' | 'excused'

export const ATTENDANCE_STATUS_LABELS: Record<AttendanceStatus, string> = {
  present: 'Присутствовал',
  absent: 'Отсутствовал',
  late: 'Опоздал',
  excused: 'Уважительная причина',
}

/**
 * `apps.academy.serializers.AttendanceSerializer`.
 *
 * The lesson roster endpoint (`GET /lessons/:id/attendance/`) returns one row
 * per active student, including students who have no Attendance row yet —
 * those come back with `id`, `status`, `status_display`, `created_at` and
 * `updated_at` all `null`, which is why those fields are nullable here.
 */
export interface AttendanceRecord {
  id: number | null
  student: number
  student_name: string
  lesson: number
  group_name: string
  lesson_date: string
  status: AttendanceStatus | null
  status_display: string | null
  comment: string
  created_at: string | null
  updated_at: string | null
}

/** Body item for `POST /lessons/:id/attendance/` (bulk upsert). */
export interface BulkAttendanceItem {
  student: number
  status: AttendanceStatus
  comment?: string
}
