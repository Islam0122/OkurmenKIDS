import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { groupsApi, type GroupListParams } from '@/api/groups'
import type { AcademicProgramInput, LessonStatus } from '@/types/academy'

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

export function useAcademicConfig(id: number | undefined, enabled = true) {
  return useQuery({
    queryKey: ['groups', 'detail', id, 'academic-config'],
    queryFn: () => groupsApi.academicConfig(id as number),
    enabled: enabled && id !== undefined,
  })
}

/** Create (`programId` null) or save one program of the group's configuration. */
export function useSaveAcademicProgram(id: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ programId, payload }: { programId: number | null; payload: AcademicProgramInput }) =>
      programId === null ? groupsApi.createProgram(id, payload) : groupsApi.saveProgram(id, programId, payload),
    onSuccess: (data) => {
      queryClient.setQueryData(['groups', 'detail', id, 'academic-config'], data)
      void queryClient.invalidateQueries({ queryKey: ['groups'] })
      void queryClient.invalidateQueries({ queryKey: ['reports'] })
      // The slot's future lessons moved on the server (schedule_lesson_sync):
      // every lesson view refetches — lesson lists and the «Расписание» week.
      void queryClient.invalidateQueries({ queryKey: ['lessons'] })
      void queryClient.invalidateQueries({ queryKey: ['schedule'] })
    },
  })
}

export function useGenerateLessons(id: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => groupsApi.generateLessons(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['groups'] })
      void queryClient.invalidateQueries({ queryKey: ['lessons'] })
      void queryClient.invalidateQueries({ queryKey: ['schedule'] })
    },
  })
}
