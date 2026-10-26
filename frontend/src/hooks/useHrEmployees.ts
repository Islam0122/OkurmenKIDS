import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { hrApi } from '@/api/hr'
import type { HREmployeeCreateInput, HREmployeeInput, HREmployeesParams } from '@/types/hr'

const KEY = 'hr-employees'

export function useHrMeta() {
  return useQuery({ queryKey: [KEY, 'meta'], queryFn: hrApi.meta, staleTime: 5 * 60_000 })
}

export function useHrEmployees(params: HREmployeesParams) {
  return useQuery({ queryKey: [KEY, 'list', params], queryFn: () => hrApi.list(params), placeholderData: keepPreviousData })
}

function useInvalidate() {
  const queryClient = useQueryClient()
  // Новый или деактивированный сотрудник меняет и отчёты посещаемости.
  return () => Promise.all([
    queryClient.invalidateQueries({ queryKey: [KEY] }),
    queryClient.invalidateQueries({ queryKey: ['staff-attendance'] }),
  ])
}

export function useSaveHrEmployee() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: ({ id, payload }: { id?: number; payload: HREmployeeCreateInput | Partial<HREmployeeInput> }) =>
      id ? hrApi.update(id, payload) : hrApi.create(payload as HREmployeeCreateInput),
    onSuccess: invalidate,
  })
}

export function useSetHrEmployeePassword() {
  return useMutation({
    mutationFn: ({ id, password, passwordConfirm }: { id: number; password: string; passwordConfirm: string }) =>
      hrApi.setPassword(id, password, passwordConfirm),
  })
}

export function useSetHrEmployeeActive() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: ({ id, active }: { id: number; active: boolean }) => hrApi.setActive(id, active),
    onSuccess: invalidate,
  })
}
