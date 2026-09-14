import { apiClient } from '@/api/client'
import type { AttendanceRecord, BulkAttendanceItem } from '@/types/attendance'
import type { Lesson, LessonStatus } from '@/types/academy'
import type { Paginated } from '@/types/common'

export interface LessonListParams {
  group?: number
  subject?: number
  status?: LessonStatus
  date?: string
  date_from?: string
  date_to?: string
  search?: string
  ordering?: string
  page?: number
}

export const lessonsApi = {
  list: (params?: LessonListParams): Promise<Paginated<Lesson>> =>
    apiClient.get<Paginated<Lesson>>('/lessons/', { params }).then((r) => r.data),

  get: (id: number): Promise<Lesson> => apiClient.get<Lesson>(`/lessons/${id}/`).then((r) => r.data),

  /** Full active-student roster for the lesson, with existing Attendance (or a not-yet-marked placeholder). */
  getAttendanceRoster: (id: number): Promise<AttendanceRecord[]> =>
    apiClient.get<AttendanceRecord[]>(`/lessons/${id}/attendance/`).then((r) => r.data),

  /** Bulk create/update Attendance for the given students in one call. */
  saveAttendance: (id: number, items: BulkAttendanceItem[]): Promise<AttendanceRecord[]> =>
    apiClient.post<AttendanceRecord[]>(`/lessons/${id}/attendance/`, items).then((r) => r.data),

  /** SCHEDULED → IN_PROGRESS. Idempotent. */
  start: (id: number): Promise<Lesson> => apiClient.post<Lesson>(`/lessons/${id}/start/`).then((r) => r.data),

  /** IN_PROGRESS → COMPLETED. Rejected (400) unless the completion checklist is satisfied. Idempotent. */
  complete: (id: number): Promise<Lesson> => apiClient.post<Lesson>(`/lessons/${id}/complete/`).then((r) => r.data),

  /** SCHEDULED/IN_PROGRESS → CANCELLED. A completed lesson can never be cancelled. Idempotent. */
  cancel: (id: number, reason?: string): Promise<Lesson> =>
    apiClient.post<Lesson>(`/lessons/${id}/cancel/`, { reason: reason ?? '' }).then((r) => r.data),

  /** Explicitly mark (or unmark) that this lesson needs no Homework. */
  setHomeworkNotRequired: (id: number, value = true): Promise<Lesson> =>
    apiClient.post<Lesson>(`/lessons/${id}/homework-not-required/`, { value }).then((r) => r.data),
}
