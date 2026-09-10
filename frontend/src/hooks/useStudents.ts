import { useQuery } from '@tanstack/react-query'

import { studentsApi, type StudentListParams } from '@/api/students'

export function useStudents(params: StudentListParams) {
  return useQuery({
    queryKey: ['students', 'list', params],
    queryFn: () => studentsApi.list(params),
  })
}

export function useStudent(id: number | undefined) {
  return useQuery({
    queryKey: ['students', 'detail', id],
    queryFn: () => studentsApi.get(id as number),
    enabled: id !== undefined,
  })
}
