import { apiClient } from '@/api/client'
import type { AttendanceRecord, AttendanceStatus } from '@/types/attendance'
import type { Paginated } from '@/types/common'

export interface AttendanceListParams {
  student?: number
  lesson?: number
  group?: number
  status?: AttendanceStatus
  date?: string
  date_from?: string
  date_to?: string
  ordering?: string
  page?: number
}

export const attendanceApi = {
  /** Direct CRUD listing — e.g. a single student's attendance history across lessons. */
  list: (params?: AttendanceListParams): Promise<Paginated<AttendanceRecord>> =>
    apiClient.get<Paginated<AttendanceRecord>>('/attendance/', { params }).then((r) => r.data),
}
