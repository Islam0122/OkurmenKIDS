import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { publicScheduleApi } from '@/api/publicSchedule'
import type { PublicScheduleParams } from '@/api/publicSchedule'

/** How often an open page re-reads the schedule (plus on window focus). */
export const PUBLIC_REFRESH_MS = 60_000

export function usePublicOptions() {
  return useQuery({ queryKey: ['public-schedule', 'options'], queryFn: publicScheduleApi.options, staleTime: 5 * 60_000 })
}

export function usePublicSchedule(params: PublicScheduleParams) {
  return useQuery({
    queryKey: ['public-schedule', 'lessons', params],
    queryFn: () => publicScheduleApi.lessons(params),
    placeholderData: keepPreviousData,
    refetchInterval: PUBLIC_REFRESH_MS,
    refetchOnWindowFocus: true,
  })
}
