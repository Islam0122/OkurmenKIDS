import { useQuery } from '@tanstack/react-query'

import { groupsApi, type GroupListParams } from '@/api/groups'
import type { LessonStatus } from '@/types/academy'

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

/** The group's recurring schedule + every dated Lesson it has, day by day. */
export function useGroupSchedule(id: number | undefined, params?: { status?: LessonStatus }) {
  return useQuery({
    queryKey: ['groups', 'schedule', id, params],
    queryFn: () => groupsApi.schedule(id as number, params),
    enabled: id !== undefined,
  })
}
