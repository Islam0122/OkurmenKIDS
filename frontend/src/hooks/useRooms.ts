import { useQuery } from '@tanstack/react-query'

import { roomsApi, type RoomAvailabilityParams, type RoomListParams } from '@/api/rooms'

export function useRooms(params?: RoomListParams) {
  return useQuery({
    queryKey: ['rooms', 'list', params],
    queryFn: () => roomsApi.list(params),
  })
}

/** Free vs. occupied rooms for a date + time window — only runs once all three are set. */
export function useRoomAvailability(params: Partial<RoomAvailabilityParams>) {
  const { date, start_time, end_time } = params
  return useQuery({
    queryKey: ['rooms', 'available', date, start_time, end_time],
    queryFn: () => roomsApi.available({ date: date as string, start_time: start_time as string, end_time: end_time as string }),
    enabled: Boolean(date && start_time && end_time),
  })
}
