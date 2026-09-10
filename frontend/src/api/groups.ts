import { apiClient } from '@/api/client'
import type { Group, GroupStatus } from '@/types/academy'
import type { Paginated } from '@/types/common'

export interface GroupListParams {
  search?: string
  course?: number
  teacher?: number
  room?: number
  status?: GroupStatus
  ordering?: string
  page?: number
}

export const groupsApi = {
  list: (params?: GroupListParams): Promise<Paginated<Group>> =>
    apiClient.get<Paginated<Group>>('/academy/groups/', { params }).then((r) => r.data),

  get: (id: number): Promise<Group> => apiClient.get<Group>(`/academy/groups/${id}/`).then((r) => r.data),
}
