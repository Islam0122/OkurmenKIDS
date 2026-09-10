import { useQuery } from '@tanstack/react-query'

import { teachersApi } from '@/api/teachers'

export function useTeacherProfile() {
  return useQuery({
    queryKey: ['teachers', 'me'],
    queryFn: () => teachersApi.me(),
  })
}
