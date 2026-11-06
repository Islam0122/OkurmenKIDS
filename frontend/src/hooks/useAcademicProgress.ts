import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { academicProgressApi } from '@/api/academicProgress'
import type { ProgramInput } from '@/types/academicProgress'

export const PROGRESS_KEY = ['academic-progress'] as const

export function useProgressMeta() {
  return useQuery({ queryKey: [...PROGRESS_KEY, 'meta'], queryFn: academicProgressApi.meta, staleTime: 60_000 })
}

export function usePrograms() {
  return useQuery({ queryKey: [...PROGRESS_KEY, 'programs'], queryFn: academicProgressApi.programs })
}

export function useProgram(id: number | null) {
  return useQuery({ queryKey: [...PROGRESS_KEY, 'program', id], queryFn: () => academicProgressApi.program(id as number), enabled: id !== null })
}

export function useGroupAcademicProgress(id: number | undefined) {
  return useQuery({ queryKey: [...PROGRESS_KEY, 'group', id], queryFn: () => academicProgressApi.group(id as number), enabled: id !== undefined })
}

/** Settings change every group's month — refresh progress and the operations group pages. */
function useInvalidateProgress() {
  const qc = useQueryClient()
  return () => {
    void qc.invalidateQueries({ queryKey: PROGRESS_KEY })
    void qc.invalidateQueries({ queryKey: ['operations'] })
  }
}

export function useSaveProgram(id: number) {
  const invalidate = useInvalidateProgress()
  return useMutation({ mutationFn: (data: ProgramInput) => academicProgressApi.saveProgram(id, data), onSuccess: invalidate })
}

export function useConfirmHistory(groupId: number) {
  const invalidate = useInvalidateProgress()
  return useMutation({ mutationFn: (n: number) => academicProgressApi.confirmHistory(groupId, n), onSuccess: invalidate })
}
