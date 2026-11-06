import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { attendanceMatrixApi } from '@/api/attendanceMatrix'
import type { CellUpdate, MatrixParams, MatrixSettings, OverviewParams } from '@/types/attendanceMatrix'

export const MATRIX_KEY = ['attendance-matrix'] as const

export function useMatrixMeta() {
  return useQuery({ queryKey: [...MATRIX_KEY, 'meta'], queryFn: attendanceMatrixApi.meta, staleTime: 60_000 })
}

export function useGroupMatrix(groupId: number | undefined, params: MatrixParams) {
  return useQuery({
    queryKey: [...MATRIX_KEY, 'group', groupId, params],
    queryFn: () => attendanceMatrixApi.group(groupId as number, params),
    enabled: groupId !== undefined,
    placeholderData: keepPreviousData,
  })
}

export function useMatrixCell(lesson: number | undefined, student: number | undefined) {
  return useQuery({
    queryKey: [...MATRIX_KEY, 'cell', lesson, student],
    queryFn: () => attendanceMatrixApi.cell(lesson as number, student as number),
    enabled: lesson !== undefined && student !== undefined,
  })
}

/** A saved cell changes the group's totals, the overview and the old
 * attendance lists — refresh everything matrix-related plus attendance. */
export function useUpdateMatrixCell() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CellUpdate) => attendanceMatrixApi.updateCell(data),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: MATRIX_KEY })
      void qc.invalidateQueries({ queryKey: ['attendance'] })
    },
  })
}

export function useMatrixOverview(params: OverviewParams, enabled = true) {
  return useQuery({
    queryKey: [...MATRIX_KEY, 'overview', params],
    queryFn: () => attendanceMatrixApi.overview(params),
    placeholderData: keepPreviousData,
    enabled,
  })
}

export function useMatrixSettings() {
  return useQuery({ queryKey: [...MATRIX_KEY, 'settings'], queryFn: attendanceMatrixApi.settings })
}

export function useUpdateMatrixSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<MatrixSettings>) => attendanceMatrixApi.updateSettings(data),
    onSuccess: () => void qc.invalidateQueries({ queryKey: MATRIX_KEY }),
  })
}
