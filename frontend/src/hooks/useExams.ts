import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { examsApi, type ExamListParams } from '@/api/exams'
import { fetchAllPages } from '@/lib/fetchAllPages'
import type { CreateExamSessionPayload } from '@/types/exams'

/** How often live data is re-fetched. The backend has no WebSocket channel,
 * so live monitoring is polling — only while something is actually running
 * and only while the tab is visible (React Query pauses hidden tabs). */
export const LIVE_REFRESH_MS = 5_000
const IDLE_REFRESH_MS = 60_000

export function useExamList(params: ExamListParams) {
  return useQuery({
    queryKey: ['exams', 'list', params],
    queryFn: () => examsApi.list(params),
    refetchInterval: (query) =>
      query.state.data?.results.some((session) => session.is_live) ? LIVE_REFRESH_MS : IDLE_REFRESH_MS,
  })
}

export function useExamParticipants(id: string | undefined) {
  return useQuery({
    queryKey: ['exams', 'detail', id, 'participants'],
    queryFn: () => examsApi.participants(id as string),
    enabled: id !== undefined,
    refetchInterval: (query) => (query.state.data?.session.is_live ? LIVE_REFRESH_MS : false),
  })
}

export function useExamParticipantResult(id: string | undefined, participantId: string | null) {
  return useQuery({
    queryKey: ['exams', 'detail', id, 'result', participantId],
    queryFn: () => examsApi.participantResult(id as string, participantId as string),
    enabled: id !== undefined && participantId !== null,
  })
}

export function useCreateExamSession() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: CreateExamSessionPayload) => examsApi.create(payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['exams'] }),
  })
}

export function useStartExamSession() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => examsApi.start(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['exams'] }),
  })
}

export function useTakeExamSession() {
  return useMutation({ mutationFn: (id: string) => examsApi.take(id) })
}

export function useMyAttempts(session?: string, enabled = true) {
  return useQuery({ queryKey: ['exams', 'my-attempts', session ?? 'all'], queryFn: () => examsApi.myAttempts(session), enabled })
}

export function useSessionTests(enabled: boolean) {
  return useQuery({
    queryKey: ['exams', 'tests'],
    queryFn: () => fetchAllPages((page) => examsApi.tests(page)),
    enabled,
    staleTime: 60_000,
  })
}
