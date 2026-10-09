import type { LessonStatus, Ref } from '@/types/assistant'

/** /api/v1/schedule/ — the Team Lead's and the Assistant's «Расписание». */

export interface ColoredRef extends Ref {
  /** The trainer's permanent schedule color, #RRGGBB. */
  color: string
}

export type ConflictKind = 'teacher' | 'room' | 'group'

export interface LessonConflict {
  kind: ConflictKind
  kind_label: string
  message: string
  /** Ids of the lessons this one overlaps. */
  with: number[]
}

export interface BoardLesson {
  id: number
  date: string
  start: string
  end: string
  duration_minutes: number
  group: Ref
  course: Ref | null
  subject: Ref | null
  teacher: ColoredRef | null
  room: Ref | null
  topic: string
  lesson_number: number
  status: LessonStatus
  status_display: string
  students_count: number | null
  schedule_overridden: boolean
  conflicts: LessonConflict[]
}

export interface LessonRef {
  id: number
  date: string
  start: string
  end: string
  group: Ref
  teacher: Ref | null
  room: Ref | null
}

export interface BoardConflict {
  kind: ConflictKind
  kind_label: string
  name: string
  date: string
  message: string
  lessons: LessonRef[]
}

export interface LegendItem extends ColoredRef {
  lessons_count: number
}

export interface FreeRoomsStat {
  mode: 'now' | 'day'
  free: number
  total: number
  date: string
  at: string | null
}

export interface ScheduleBoardData {
  start: string
  end: string
  now: { date: string; time: string; timezone: string }
  hours: { start: string; end: string }
  capabilities: { can_edit: boolean }
  lessons: BoardLesson[]
  legend: LegendItem[]
  conflicts: BoardConflict[]
  stats: {
    lessons: number
    by_status: Partial<Record<LessonStatus, number>>
    conflicts: number
    minutes: number
    free_rooms: FreeRoomsStat | null
  }
}

export interface ScheduleOptions {
  teachers: ColoredRef[]
  rooms: { id: number; name: string; capacity: number | null }[]
  groups: { id: number; name: string; course: string }[]
  statuses: { value: LessonStatus; label: string }[]
  hours: { start: string; end: string }
}

export interface RoomAvailabilityRow {
  room: { id: number; name: string; capacity: number | null }
  is_free: boolean
  lessons_count: number
  busy: { start: string; end: string }[]
  conflicting_lessons: LessonRef[]
  /** Busy room: when it frees up. */
  free_at: string | null
  /** Free room: how long it stays free around the window. */
  free_window: { start: string; end: string } | null
  /** Busy room: the next free interval long enough for the window. */
  next_free: { start: string; end: string } | null
}

export interface FreeRoomsData {
  date: string
  start: string
  end: string
  free_count: number
  busy_count: number
  rooms: RoomAvailabilityRow[]
}

export interface ConflictCheckResult {
  date: string
  start: string
  end: string
  ok: boolean
  conflicts: { kind: ConflictKind; kind_label: string; message: string; lesson: LessonRef }[]
}

export interface BoardParams {
  start: string
  end: string
  teacher?: number
  room?: number[]
  group?: number
}
