import { apiClient } from '@/api/client'
import type { Student } from '@/types/academy'
import type { Paginated } from '@/types/common'

export interface StudentListParams {
  search?: string
  group?: number
  is_active?: boolean
  ordering?: string
  page?: number
}

export const studentsApi = {
  list: (params?: StudentListParams): Promise<Paginated<Student>> =>
    apiClient.get<Paginated<Student>>('/academy/students/', { params }).then((r) => r.data),

  get: (id: number): Promise<Student> => apiClient.get<Student>(`/academy/students/${id}/`).then((r) => r.data),
}
