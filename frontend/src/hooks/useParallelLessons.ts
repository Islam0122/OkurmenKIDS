import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { parallelLessonsApi } from '@/api/parallelLessons'
import { SCHEDULE_KEY } from '@/hooks/useSchedule'
import type { SessionInput, SessionListParams } from '@/types/parallelLessons'

/** Every parallel-session query lives under one key root; a write refreshes
 * it and the schedule board (the sessions' lessons are on it too). */
export const PARALLEL_KEY = ['parallel-lessons'] as const

export function useParallelSessions(params: SessionListParams) {
  return useQuery({ queryKey: [...PARALLEL_KEY, 'list', params], queryFn: () => parallelLessonsApi.list(params), placeholderData: keepPreviousData })
}

export function useParallelSession(id: number) {
  return useQuery({ queryKey: [...PARALLEL_KEY, 'detail', id], queryFn: () => parallelLessonsApi.get(id), enabled: id > 0 })
}

export function useParallelOptions(enabled = true) {
  return useQuery({ queryKey: [...PARALLEL_KEY, 'options'], queryFn: parallelLessonsApi.options, staleTime: 5 * 60_000, enabled })
}

export function useSessionRoster(id: number) {
  return useQuery({ queryKey: [...PARALLEL_KEY, 'roster', id], queryFn: () => parallelLessonsApi.roster(id) })
}

export function useSessionStatistics(id: number) {
  return useQuery({ queryKey: [...PARALLEL_KEY, 'statistics', id], queryFn: () => parallelLessonsApi.statistics(id) })
}

export function useSessionHomework(id: number) {
  return useQuery({ queryKey: [...PARALLEL_KEY, 'homework', id], queryFn: () => parallelLessonsApi.homework(id) })
}

export function useSessionHistory(id: number) {
  return useQuery({ queryKey: [...PARALLEL_KEY, 'history', id], queryFn: () => parallelLessonsApi.history(id) })
}

export function useParallelAnalytics(params: { start: string; end: string; teacher?: number }) {
  return useQuery({ queryKey: [...PARALLEL_KEY, 'analytics', params], queryFn: () => parallelLessonsApi.analytics(params), placeholderData: keepPreviousData })
}

/** The live preview of the backend's own conflict check (the save repeats it). */
export function useSessionConflictCheck(body: Partial<SessionInput> & { session?: number }, enabled: boolean) {
  return useQuery({
    queryKey: [...PARALLEL_KEY, 'check', body],
    queryFn: () => parallelLessonsApi.check(body),
    enabled,
    placeholderData: keepPreviousData,
  })
}

export function useParallelMutation<TArgs, TResult>(fn: (args: TArgs) => Promise<TResult>) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: PARALLEL_KEY })
      void client.invalidateQueries({ queryKey: SCHEDULE_KEY })
    },
  })
}
