import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { scheduleApi } from '@/api/schedule'
import type { BoardParams } from '@/types/schedule'

/** Every schedule-board query lives under one key root; Assistant writes
 * (move / cancel / a new slot) refresh it (see useAssistantMutation). */
export const SCHEDULE_KEY = ['schedule-board'] as const

export function useScheduleOptions() {
  return useQuery({ queryKey: [...SCHEDULE_KEY, 'options'], queryFn: scheduleApi.options, staleTime: 5 * 60_000 })
}

/** `refreshMs` — how often the open page re-reads the schedule (default
 * 5 minutes); it is also re-read whenever the window regains focus. */
export function useScheduleBoard(params: BoardParams, { refreshMs = 5 * 60_000 }: { refreshMs?: number } = {}) {
  return useQuery({
    queryKey: [...SCHEDULE_KEY, 'board', params],
    queryFn: () => scheduleApi.board(params),
    placeholderData: keepPreviousData,
    refetchInterval: refreshMs,
    refetchOnWindowFocus: true,
  })
}

export function useFreeRooms(params: { date: string; start: string; end: string }, enabled = true) {
  return useQuery({
    queryKey: [...SCHEDULE_KEY, 'free-rooms', params],
    queryFn: () => scheduleApi.freeRooms(params),
    enabled: enabled && Boolean(params.date && params.start && params.end) && params.end > params.start,
    placeholderData: keepPreviousData,
  })
}

/** The move form's live check — the backend still refuses a clash on save. */
export function useConflictCheck(params: { date: string; start: string; end: string; lesson?: number }, enabled = true) {
  return useQuery({
    queryKey: [...SCHEDULE_KEY, 'check', params],
    queryFn: () => scheduleApi.check(params),
    enabled: enabled && Boolean(params.date && params.start && params.end) && params.end > params.start,
    staleTime: 10_000,
  })
}
