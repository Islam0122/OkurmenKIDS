import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { controlApi, type ControlDetailParams, type ControlParams } from '@/api/control'

/** Recomputed from real Lesson/Attendance/Homework rows on every call. */
export function useControlOverview(params: ControlParams) {
  return useQuery({
    queryKey: ['control', 'overview', params],
    queryFn: () => controlApi.overview(params),
    placeholderData: keepPreviousData,
  })
}

export function useControlDetail(params: ControlDetailParams | null) {
  return useQuery({
    queryKey: ['control', 'detail', params],
    queryFn: () => controlApi.detail(params as ControlDetailParams),
    enabled: params !== null,
  })
}
