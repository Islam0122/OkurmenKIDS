import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  homeworkApi,
  homeworkResultsApi,
  type CreateHomeworkPayload,
  type HomeworkListParams,
  type HomeworkResultListParams,
} from '@/api/homework'
import type { BulkHomeworkResultItem } from '@/types/homework'

export function useHomeworkList(params: HomeworkListParams) {
  return useQuery({
    queryKey: ['homework', 'list', params],
    queryFn: () => homeworkApi.list(params),
  })
}

export function useHomeworkDetail(id: number | undefined) {
  return useQuery({
    queryKey: ['homework', 'detail', id],
    queryFn: () => homeworkApi.get(id as number),
    enabled: id !== undefined,
  })
}

export function useHomeworkResultsRoster(homeworkId: number | undefined) {
  return useQuery({
    queryKey: ['homework', 'detail', homeworkId, 'results'],
    queryFn: () => homeworkApi.getResultsRoster(homeworkId as number),
    enabled: homeworkId !== undefined,
  })
}

export function useHomeworkResultsList(params: HomeworkResultListParams) {
  return useQuery({
    queryKey: ['homework-results', 'list', params],
    queryFn: () => homeworkResultsApi.list(params),
  })
}

export function useCreateHomework() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: CreateHomeworkPayload) => homeworkApi.create(payload),
    onSuccess: (_data, payload) => {
      void queryClient.invalidateQueries({ queryKey: ['homework', 'list'] })
      void queryClient.invalidateQueries({ queryKey: ['lessons', 'detail', payload.lesson] })
      void queryClient.invalidateQueries({ queryKey: ['lessons', 'list'] })
    },
  })
}

/** `lessonId` is optional only because it isn't known until `useHomeworkDetail`
 * resolves — pass `homework?.lesson` from the caller; once the homework has
 * loaded (the only time a save can actually happen), it's always present. */
export function useSaveHomeworkResults(homeworkId: number, lessonId?: number) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (items: BulkHomeworkResultItem[]) => homeworkApi.saveResults(homeworkId, items),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['homework', 'detail', homeworkId] })
      void queryClient.invalidateQueries({ queryKey: ['homework', 'list'] })
      void queryClient.invalidateQueries({ queryKey: ['homework-results'] })
      void queryClient.invalidateQueries({ queryKey: ['kpi'] })
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      // Grading doesn't change the lesson's own completion requirements
      // (only *having* Homework does — see useCreateHomework), but the
      // Lesson Detail page the teacher lands back on shows this homework's
      // results_count too — refresh it for consistency regardless.
      if (lessonId !== undefined) {
        void queryClient.invalidateQueries({ queryKey: ['lessons', 'detail', lessonId] })
        void queryClient.invalidateQueries({ queryKey: ['lessons', 'list'] })
      }
    },
  })
}
