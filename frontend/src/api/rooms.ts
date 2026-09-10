import { apiClient } from '@/api/client'
import type { Room, RoomAvailability } from '@/types/academy'
import type { Paginated } from '@/types/common'

export interface RoomListParams {
  search?: string
  is_active?: boolean
  ordering?: string
  page?: number
}

export interface RoomAvailabilityParams {
  date: string
  start_time: string
  end_time: string
}

export const roomsApi = {
  list: (params?: RoomListParams): Promise<Paginated<Room>> =>
    apiClient.get<Paginated<Room>>('/academy/rooms/', { params }).then((r) => r.data),

  /** Free vs. occupied rooms for a given date + time window (based on existing Lessons). */
  available: (params: RoomAvailabilityParams): Promise<RoomAvailability> =>
    apiClient.get<RoomAvailability>('/academy/rooms/available/', { params }).then((r) => r.data),
}
