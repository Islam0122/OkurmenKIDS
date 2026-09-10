import { apiClient } from '@/api/client'
import type { Paginated, Subject } from '@/types'

export interface SubjectListParams {
  search?: string
  is_active?: boolean
  ordering?: string
  page?: number
}

export const subjectsApi = {
  list: (params?: SubjectListParams): Promise<Paginated<Subject>> =>
    apiClient.get<Paginated<Subject>>('/users/subject/', { params }).then((r) => r.data),
}
