import type { UserRole } from '@/types/auth'

/** Учёт прихода и ухода сотрудников (backend: apps.staff_attendance,
 * /api/v1/staff-attendance/). Не путать с `types/attendance` — это
 * посещаемость студентов на занятиях. Все времена приходят ISO-строкой
 * со смещением часового пояса офиса. */

export interface Employee {
  id: number
  full_name: string
  username: string
  role: UserRole
  role_label: string
  photo_url: string | null
}

export type SessionStatus = 'open' | 'closed' | 'missing_checkout'

export interface WorkSession {
  id: number
  work_date: string
  checked_in_at: string
  checked_out_at: string | null
  status: SessionStatus
  status_label: string
  source: 'qr' | 'manual'
  duration_seconds: number | null
  expected_start: string | null
  late_minutes: number
  is_adjusted: boolean
  location: { id: number; name: string } | null
  check_in_distance_m: number | null
  check_out_distance_m: number | null
}

export type DayStatus = 'not_arrived' | 'at_work' | 'day_finished' | 'no_check_in' | 'no_check_out' | 'day_off' | 'not_tracked'
export type StatusFilter = DayStatus | 'late' | 'adjusted'

export interface DayRow {
  key: string
  employee: Employee
  date: string
  status: DayStatus
  status_label: string
  check_in: string | null
  check_out: string | null
  duration_seconds: number | null
  late_minutes: number
  is_late: boolean
  is_adjusted: boolean
  expected_start: string | null
  expected_end: string | null
  sessions_count: number
  last_session_id: number | null
  locations: string[]
  sessions: WorkSession[]
}

export type WorkdayState = 'not_arrived' | 'at_work' | 'day_finished'
export type MarkKind = 'check_in' | 'check_out'

export interface AttendanceAccess {
  can_view_reports: boolean
  can_adjust: boolean
  can_manage: boolean
}

/** `GET /staff-attendance/me/status/` */
export interface MyStatus {
  employee: Employee
  state: WorkdayState
  next_action: MarkKind
  server_time: string
  timezone: string
  today: DayRow
  open_session: WorkSession | null
  stale_session: WorkSession | null
  access: AttendanceAccess
}

export interface MonthStats {
  year: number
  month: number
  days_present: number
  work_days: number
  late_days: number
  late_minutes_total: number
  no_check_in_days: number
  no_check_out_days: number
  adjusted_days: number
  total_seconds: number
  average_seconds: number
}

export interface OfficeInfo {
  code: string
  name: string
  address: string
  radius_m: number
}

export interface MarkPayload {
  location_code: string
  latitude: number
  longitude: number
  accuracy: number
  idempotency_key: string
}

/** Ответ на успешную отметку (201, или 200 для повтора того же запроса). */
export interface MarkResult {
  event: MarkKind
  replayed: boolean
  employee: Employee
  occurred_at: string
  timezone: string
  location: { name: string | null }
  distance_m: number | null
  session: WorkSession
  closed_stale_session: WorkSession | null
}

/** Тело отказа отметки: понятный текст + машинный код. */
export interface MarkErrorBody {
  detail: string
  code: string
  distance_m?: number
  radius_m?: number
  accuracy_m?: number
  max_accuracy_m?: number
}

export interface AdminMeta {
  timezone: string
  today: string
  roles: { value: UserRole; label: string }[]
  statuses: { value: StatusFilter; label: string }[]
  locations: { id: number; name: string; is_active: boolean }[]
  access: AttendanceAccess & { scope: 'all' | 'teachers' }
}

export interface Overview {
  date: string
  total_employees: number
  arrived: number
  at_work: number
  late: number
  finished: number
  not_arrived: number
  no_check_in: number
  no_check_out: number
  day_off: number
  not_tracked: number
  adjusted: number
}

export interface RecordsParams {
  date?: string
  date_from?: string
  date_to?: string
  search?: string
  role?: string
  status?: string
  location?: string
  ordering?: string
  page?: number
  page_size?: number
}

export interface AttendanceEventItem {
  id: number
  session: number
  kind: 'check_in' | 'check_out' | 'auto_close' | 'manual_create'
  kind_label: string
  occurred_at: string
  location_name: string | null
  distance_m: number | null
  accuracy_m: number | null
  created_by_name: string | null
}

export interface SessionSnapshot {
  work_date?: string | null
  checked_in_at?: string | null
  checked_out_at?: string | null
  status?: SessionStatus
  late_minutes?: number
  location_id?: number | null
}

export interface Adjustment {
  id: number
  session: number
  action: 'create' | 'update'
  action_label: string
  old_values: SessionSnapshot
  new_values: SessionSnapshot
  reason: string
  adjusted_by: number
  adjusted_by_name: string
  employee: Employee
  created_at: string
}

export interface EmployeeCard {
  employee: Employee & { email: string; is_active: boolean }
  date_from: string
  date_to: string
  stats: {
    days_present: number
    late_days: number
    late_minutes_total: number
    no_check_in_days: number
    no_check_out_days: number
    total_seconds: number
  }
  days: DayRow[]
  events: AttendanceEventItem[]
  adjustments: Adjustment[]
}

export interface AdjustPayload {
  checked_in_at: string
  checked_out_at: string | null
  reason: string
  location?: number | null
  late_minutes?: number | null
}

export interface ManualSessionPayload extends AdjustPayload {
  user: number
}

export interface OfficeLocation {
  id: number
  name: string
  address: string
  code: string
  latitude: number
  longitude: number
  radius_m: number
  is_active: boolean
  qr_url: string
  created_at: string
  updated_at: string
}

export type OfficeLocationInput = Pick<OfficeLocation, 'name' | 'address' | 'latitude' | 'longitude' | 'radius_m' | 'is_active'>

export interface AttendanceSettings {
  timezone: string
  max_gps_accuracy_m: number
  work_start: string
  work_end: string
  work_days: number[]
  late_grace_minutes: number
  tracked_roles: UserRole[]
  teacher_schedule_from_lessons: boolean
  teacher_arrival_before_lesson_minutes: number
  /** Дни раньше этой даты не считаются пропусками. */
  tracking_started_on: string
  network_check_enabled: boolean
  office_networks: string
  updated_at: string
  updated_by_name: string | null
}

export interface WorkSchedule {
  id: number
  user: number
  employee: Employee
  work_start: string
  work_end: string
  work_days: number[]
  late_grace_minutes: number | null
  is_active: boolean
  note: string
  updated_at: string
}

export type WorkScheduleInput = Pick<WorkSchedule, 'work_start' | 'work_end' | 'work_days' | 'late_grace_minutes' | 'is_active' | 'note'>
