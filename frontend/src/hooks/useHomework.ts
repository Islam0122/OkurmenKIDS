import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { homeworkApi, homeworkResultsApi, type HomeworkListParams, type HomeworkResultListParams } from '@/api/homework'
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

export function useSaveHomeworkResults(homeworkId: number) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (items: BulkHomeworkResultItem[]) => homeworkApi.saveResults(homeworkId, items),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['homework', 'detail', homeworkId] })
      void queryClient.invalidateQueries({ queryKey: ['homework', 'list'] })
      void queryClient.invalidateQueries({ queryKey: ['homework-results'] })
      void queryClient.invalidateQueries({ queryKey: ['kpi'] })
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}
