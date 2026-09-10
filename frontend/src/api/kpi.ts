import { apiClient } from '@/api/client'
import type { Paginated } from '@/types/common'
import type { KPIAttendance, KPIGroup, KPIHomework, KPILesson, KPIStudent, KPITeacher } from '@/types/kpi'

/** Every KPI list is read-only for a Teacher, scoped server-side to their own groups/students. */
export interface KPIListParams {
  group?: number
  teacher?: number
  student?: number
  lesson?: number
  date_from?: string
  date_to?: string
  ordering?: string
  page?: number
}

export const kpiApi = {
  groups: (params?: KPIListParams): Promise<Paginated<KPIGroup>> =>
    apiClient.get<Paginated<KPIGroup>>('/academy/kpi/groups/', { params }).then((r) => r.data),

  teachers: (params?: KPIListParams): Promise<Paginated<KPITeacher>> =>
    apiClient.get<Paginated<KPITeacher>>('/academy/kpi/teachers/', { params }).then((r) => r.data),

  students: (params?: KPIListParams): Promise<Paginated<KPIStudent>> =>
    apiClient.get<Paginated<KPIStudent>>('/academy/kpi/students/', { params }).then((r) => r.data),

  lessons: (params?: KPIListParams): Promise<Paginated<KPILesson>> =>
    apiClient.get<Paginated<KPILesson>>('/academy/kpi/lessons/', { params }).then((r) => r.data),

  attendance: (params?: KPIListParams): Promise<Paginated<KPIAttendance>> =>
    apiClient.get<Paginated<KPIAttendance>>('/academy/kpi/attendance/', { params }).then((r) => r.data),

  homework: (params?: KPIListParams): Promise<Paginated<KPIHomework>> =>
    apiClient.get<Paginated<KPIHomework>>('/academy/kpi/homework/', { params }).then((r) => r.data),
}
