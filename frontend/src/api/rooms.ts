import { apiClient } from '@/api/client'
import type { Room } from '@/types/academy'
import type { Paginated } from '@/types/common'

export interface RoomListParams {
  search?: string
  is_active?: boolean
  ordering?: string
  page?: number
}

export const roomsApi = {
  list: (params?: RoomListParams): Promise<Paginated<Room>> =>
    apiClient.get<Paginated<Room>>('/academy/rooms/', { params }).then((r) => r.data),
}
