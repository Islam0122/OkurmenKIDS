import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { staffAttendanceApi } from '@/api/staffAttendance'
import type {
  AdjustPayload,
  AttendanceSettings,
  ManualSessionPayload,
  OfficeLocationInput,
  RecordsParams,
  WorkScheduleInput,
} from '@/types/staffAttendance'

const KEY = 'staff-attendance'

export function useMyAttendanceStatus() {
  return useQuery({ queryKey: [KEY, 'me', 'status'], queryFn: staffAttendanceApi.myStatus, refetchInterval: 60_000 })
}

export function useMyAttendanceHistory(params: { date_from?: string; date_to?: string; page?: number }) {
  return useQuery({
    queryKey: [KEY, 'me', 'history', params],
    queryFn: () => staffAttendanceApi.myHistory(params),
    placeholderData: keepPreviousData,
  })
}

export function useMyAttendanceStats(month: string) {
  return useQuery({ queryKey: [KEY, 'me', 'stats', month], queryFn: () => staffAttendanceApi.myStats(month) })
}

export function useAttendanceMeta(enabled = true) {
  return useQuery({ queryKey: [KEY, 'meta'], queryFn: staffAttendanceApi.meta, staleTime: 60_000, retry: false, enabled })
}

export function useAttendanceOverview(params: RecordsParams) {
  return useQuery({
    queryKey: [KEY, 'overview', params],
    queryFn: () => staffAttendanceApi.overview(params),
    placeholderData: keepPreviousData,
  })
}

export function useAttendanceRecords(params: RecordsParams) {
  return useQuery({
    queryKey: [KEY, 'records', params],
    queryFn: () => staffAttendanceApi.records(params),
    placeholderData: keepPreviousData,
  })
}

export function useEmployeeAttendance(id: number | null, params: { date_from?: string; date_to?: string }) {
  return useQuery({
    queryKey: [KEY, 'employee', id, params],
    queryFn: () => staffAttendanceApi.employee(id as number, params),
    enabled: id !== null,
  })
}

export function useOfficeLocations() {
  return useQuery({ queryKey: [KEY, 'locations'], queryFn: staffAttendanceApi.locations })
}

export function useAttendanceSettings() {
  return useQuery({ queryKey: [KEY, 'settings'], queryFn: staffAttendanceApi.settings })
}

export function useWorkSchedules() {
  return useQuery({ queryKey: [KEY, 'schedules'], queryFn: staffAttendanceApi.schedules })
}

function useInvalidate() {
  const queryClient = useQueryClient()
  return () => void queryClient.invalidateQueries({ queryKey: [KEY] })
}

export function useAdjustSession() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: ({ sessionId, payload }: { sessionId: number; payload: AdjustPayload }) =>
      staffAttendanceApi.adjust(sessionId, payload),
    onSuccess: invalidate,
  })
}

export function useCreateManualSession() {
  const invalidate = useInvalidate()
  return useMutation({ mutationFn: (payload: ManualSessionPayload) => staffAttendanceApi.createManual(payload), onSuccess: invalidate })
}

export function useSaveLocation() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: ({ id, payload }: { id?: number; payload: Partial<OfficeLocationInput> }) =>
      id ? staffAttendanceApi.updateLocation(id, payload) : staffAttendanceApi.createLocation(payload as OfficeLocationInput),
    onSuccess: invalidate,
  })
}

export function useUpdateAttendanceSettings() {
  const invalidate = useInvalidate()
  return useMutation({ mutationFn: (payload: Partial<AttendanceSettings>) => staffAttendanceApi.updateSettings(payload), onSuccess: invalidate })
}

export function useSaveWorkSchedule() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: ({ userId, payload }: { userId: number; payload: WorkScheduleInput }) => staffAttendanceApi.saveSchedule(userId, payload),
    onSuccess: invalidate,
  })
}

export function useDeleteWorkSchedule() {
  const invalidate = useInvalidate()
  return useMutation({ mutationFn: (userId: number) => staffAttendanceApi.deleteSchedule(userId), onSuccess: invalidate })
}

/** После отметки обновить статус, историю и статистику. */
export function useRefreshMyAttendance() {
  const queryClient = useQueryClient()
  return () => void queryClient.invalidateQueries({ queryKey: [KEY, 'me'] })
}
