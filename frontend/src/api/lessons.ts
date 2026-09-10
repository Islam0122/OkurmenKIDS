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
    apiClient.get<Paginated<Lesson>>('/academy/lessons/', { params }).then((r) => r.data),

  get: (id: number): Promise<Lesson> => apiClient.get<Lesson>(`/academy/lessons/${id}/`).then((r) => r.data),

  /** Full active-student roster for the lesson, with existing Attendance (or a not-yet-marked placeholder). */
  getAttendanceRoster: (id: number): Promise<AttendanceRecord[]> =>
    apiClient.get<AttendanceRecord[]>(`/academy/lessons/${id}/attendance/`).then((r) => r.data),

  /** Bulk create/update Attendance for the given students in one call. */
  saveAttendance: (id: number, items: BulkAttendanceItem[]): Promise<AttendanceRecord[]> =>
    apiClient.post<AttendanceRecord[]>(`/academy/lessons/${id}/attendance/`, items).then((r) => r.data),
}
