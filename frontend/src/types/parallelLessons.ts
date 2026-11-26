/** «Параллельные занятия» — apps.academy.parallel_session_serializers /
 * services.parallel_sessions. Several groups, one room, one shared trainer:
 * ONE lesson; every group keeps its own lesson (attendance, homework). */
import type { Ref } from './assistant'

export type SessionStatus = 'scheduled' | 'in_progress' | 'completed' | 'cancelled'
export type AttendanceMark = 'present' | 'absent' | 'late' | 'excused'

export interface SessionParticipant {
  id: number
  group: Ref
  lesson: number | null
  lesson_status: string | null
  program: { id: number; subject: string | null } | null
  status: 'active' | 'removed'
  status_display: string
  students_count: number
  added_at: string
  removed_at: string | null
  removal_reason: string
}

export interface SessionCapabilities {
  can_edit: boolean
  can_change_schedule: boolean
  can_manage_groups: boolean
  can_cancel: boolean
  can_start: boolean
  can_complete: boolean
  can_mark_attendance: boolean
  can_add_homework: boolean
}

export interface ParallelSession {
  id: number
  date: string
  start_time: string
  end_time: string
  teacher: Ref & { color: string | null }
  room: Ref
  subject: Ref | null
  topic: string
  description: string
  notes: string
  youtube_url: string
  presentation_urls: string[]
  status: SessionStatus
  status_display: string
  cancellation_reason: string
  groups: SessionParticipant[]
  groups_count: number
  students_count: number
  created_by_name: string | null
  completed_at: string | null
  completed_by_name: string | null
  cancelled_at: string | null
  created_at: string
  updated_at: string
  capabilities: SessionCapabilities
}

export interface SessionInput {
  teacher: number
  room: number
  subject?: number | null
  date: string
  start_time: string
  end_time: string
  groups: number[]
  topic?: string
  description?: string
  notes?: string
  youtube_url?: string
  presentation_urls?: string[]
}

export interface SessionConflict {
  kind: 'teacher' | 'room' | 'group'
  kind_label: string
  message: string
}

export interface ConflictCheck {
  ok: boolean
  conflicts: SessionConflict[]
}

export interface RosterStudent {
  student: number
  student_name: string
  status: AttendanceMark | null
  status_display: string | null
  comment: string
  excuse_reason: string
}

export interface RosterGroup {
  group: Ref
  lesson: number
  lesson_status: string
  students: RosterStudent[]
}

export interface GroupStats {
  group: Ref
  lesson: number
  lesson_status: string
  students: number
  marked: number
  present: number
  absent: number
  late: number
  excused: number
  attendance_rate: number | null
  homework: number
  homework_results: Record<string, number>
}

export interface SessionStatistics {
  session: number
  status: SessionStatus
  groups: GroupStats[]
  totals: { students: number; marked: number; present: number; absent: number; late: number; excused: number; attendance_rate: number | null; groups: number }
}

export interface SessionHistoryEntry {
  at: string
  user: string | null
  action: 'created' | 'changed'
  message: string
}

export interface SessionHomework {
  id: number
  lesson: number
  group_name: string
  title: string
  description: string
  deadline: string | null
}

export interface ParallelAnalytics {
  start: string
  end: string
  totals: { sessions: number; scheduled: number; in_progress: number; completed: number; cancelled: number; group_participations: number; groups: number; students: number }
  workload: { teacher: Ref; sessions: number; completed: number; groups: number; minutes: number }[]
  attendance_by_group: { group: Ref; present: number; absent: number; late: number; excused: number; marked: number; attendance_rate: number | null }[]
}

export interface ParallelOptions {
  teachers: (Ref & { color: string | null })[]
  rooms: (Ref & { capacity: number | null })[]
  groups: (Ref & { course: string; students_count: number })[]
  subjects: Ref[]
  statuses: { value: SessionStatus; label: string }[]
}

export interface SessionListParams {
  page?: number
  date?: string
  date_from?: string
  date_to?: string
  teacher?: number
  room?: number
  group?: number
  status?: SessionStatus
}
