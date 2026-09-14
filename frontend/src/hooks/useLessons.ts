import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { lessonsApi, type LessonListParams } from '@/api/lessons'

export function useLessons(params: LessonListParams) {
  return useQuery({
    queryKey: ['lessons', 'list', params],
    queryFn: () => lessonsApi.list(params),
  })
}

export function useLesson(id: number | undefined) {
  return useQuery({
    queryKey: ['lessons', 'detail', id],
    queryFn: () => lessonsApi.get(id as number),
    enabled: id !== undefined,
  })
}

/** Shared invalidation for every lesson-lifecycle mutation (start/complete/
 * cancel/homework-not-required) — each one changes the lesson's status, so
 * every list/tab/KPI that reads it needs to refetch. */
function useLessonLifecycleMutation(mutationFn: (id: number) => Promise<unknown>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn,
    onSuccess: (_data, id) => {
      void queryClient.invalidateQueries({ queryKey: ['lessons'] })
      void queryClient.invalidateQueries({ queryKey: ['lessons', 'detail', id] })
      void queryClient.invalidateQueries({ queryKey: ['kpi'] })
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}

export function useStartLesson() {
  return useLessonLifecycleMutation((id: number) => lessonsApi.start(id))
}

export function useCompleteLesson() {
  return useLessonLifecycleMutation((id: number) => lessonsApi.complete(id))
}

export function useCancelLesson() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, reason }: { id: number; reason?: string }) => lessonsApi.cancel(id, reason),
    onSuccess: (_data, { id }) => {
      void queryClient.invalidateQueries({ queryKey: ['lessons'] })
      void queryClient.invalidateQueries({ queryKey: ['lessons', 'detail', id] })
      void queryClient.invalidateQueries({ queryKey: ['kpi'] })
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}

export function useSetHomeworkNotRequired() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, value }: { id: number; value: boolean }) => lessonsApi.setHomeworkNotRequired(id, value),
    onSuccess: (_data, { id }) => {
      void queryClient.invalidateQueries({ queryKey: ['lessons', 'detail', id] })
      void queryClient.invalidateQueries({ queryKey: ['lessons', 'list'] })
    },
  })
}
