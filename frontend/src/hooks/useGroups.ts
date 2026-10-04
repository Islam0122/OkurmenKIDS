import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { groupsApi, type GroupListParams } from '@/api/groups'
import type { AssignTrainerPayload, LessonStatus } from '@/types/academy'

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

export function useTrainerAssignments(id: number | undefined, enabled = true) {
  return useQuery({
    queryKey: ['groups', 'detail', id, 'trainer-assignments'],
    queryFn: () => groupsApi.trainerAssignments(id as number),
    enabled: enabled && id !== undefined,
  })
}

export function useAssignTrainer(id: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: AssignTrainerPayload) => groupsApi.assignTrainer(id, payload),
    onSuccess: (data) => {
      queryClient.setQueryData(['groups', 'detail', id, 'trainer-assignments'], data)
      // Programs, schedule, lessons and every report follow the new trainer.
      void queryClient.invalidateQueries({ queryKey: ['groups'] })
      void queryClient.invalidateQueries({ queryKey: ['reports'] })
      void queryClient.invalidateQueries({ queryKey: ['lessons'] })
    },
  })
}
