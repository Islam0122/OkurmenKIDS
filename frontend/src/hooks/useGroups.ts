import { useQuery } from '@tanstack/react-query'

import { groupsApi, type GroupListParams } from '@/api/groups'

export function useGroups(params: GroupListParams) {
  return useQuery({
    queryKey: ['groups', 'list', params],
    queryFn: () => groupsApi.list(params),
  })
}

export function useGroup(id: number | undefined) {
  return useQuery({
    queryKey: ['groups', 'detail', id],
    queryFn: () => groupsApi.get(id as number),
    enabled: id !== undefined,
  })
}
