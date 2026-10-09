import { apiClient } from '@/api/client'
import type { BoardParams, ConflictCheckResult, FreeRoomsData, ScheduleBoardData, ScheduleOptions } from '@/types/schedule'

const get = <T>(url: string, params?: object) => apiClient.get<T>(`/schedule${url}`, { params }).then((r) => r.data)

export const scheduleApi = {
  options: () => get<ScheduleOptions>('/options/'),
  /** Rooms go as one comma-separated `room=1,2` param. */
  board: ({ room, ...params }: BoardParams) => get<ScheduleBoardData>('/board/', { ...params, room: room?.length ? room.join(',') : undefined }),
  freeRooms: (params: { date: string; start: string; end: string }) => get<FreeRoomsData>('/free-rooms/', params),
  check: (params: { date: string; start: string; end: string; lesson?: number; teacher?: number; room?: number; group?: number }) =>
    get<ConflictCheckResult>('/check/', params),
}
