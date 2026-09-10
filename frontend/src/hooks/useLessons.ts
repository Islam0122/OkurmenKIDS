import { useQuery } from '@tanstack/react-query'

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
