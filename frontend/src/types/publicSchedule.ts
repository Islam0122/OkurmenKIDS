/** /api/v1/public/schedule/ — the published schedule (no login). Only these
 * fields exist: no ids (opaque `key`s), no personal data. */

export type PublicLessonStatus = 'scheduled' | 'in_progress' | 'completed' | 'cancelled'

export interface PublicRef {
  key: string
  name: string
}

export interface PublicTrainer extends PublicRef {
  color: string | null
}

export interface PublicLesson {
  key: string
  date: string
  start: string
  end: string
  duration_minutes: number
  group: PublicRef
  course: string
  subject: string | null
  status: PublicLessonStatus
  status_label: string
  rescheduled: boolean
  /** Absent when the academy doesn't publish trainers / rooms. */
  trainer?: PublicTrainer | null
  room?: PublicRef | null
}

export interface PublicSchedule {
  start: string
  end: string
  now: { date: string; time: string; timezone: string }
  hours: { start: string; end: string }
  show: { trainers: boolean; rooms: boolean }
  lessons: PublicLesson[]
}

export interface PublicOptions {
  today: string
  window: { first: string; last: string; max_days: number }
  hours: { start: string; end: string }
  show: { trainers: boolean; rooms: boolean }
  groups: (PublicRef & { course: string })[]
  trainers: PublicTrainer[]
  rooms: PublicRef[]
}
