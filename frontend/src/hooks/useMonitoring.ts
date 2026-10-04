import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { monitoringApi } from '@/api/monitoring'
import type { MonitoringFilters } from '@/types/monitoring'

/** Live monitoring is polled (no WebSocket channel in the backend yet).
 * Only the query functions below would change to switch to a push channel.
 * React Query pauses polling while the tab is hidden. */
export const MONITORING_REFRESH_MS = 15_000

export function useMonitoringOverview(filters: MonitoringFilters) {
  return useQuery({
    queryKey: ['monitoring', 'overview', filters],
    queryFn: () => monitoringApi.overview(filters),
    refetchInterval: MONITORING_REFRESH_MS,
  })
}

export function useMonitoringAttempts(filters: MonitoringFilters) {
  return useQuery({
    queryKey: ['monitoring', 'attempts', filters],
    queryFn: () => monitoringApi.attempts(filters),
    refetchInterval: MONITORING_REFRESH_MS,
    placeholderData: keepPreviousData,
  })
}

export function useMonitoringAttempt(id: string | null) {
  return useQuery({
    queryKey: ['monitoring', 'attempt', id],
    queryFn: () => monitoringApi.attempt(id as string),
    enabled: id !== null,
    refetchInterval: (query) => (query.state.data?.status === 'in_progress' ? MONITORING_REFRESH_MS : false),
  })
}

export function useMonitoringFilterOptions() {
  return useQuery({ queryKey: ['monitoring', 'filters'], queryFn: monitoringApi.filters, staleTime: 5 * 60_000 })
}

export function useTeacherPerformance(filters: MonitoringFilters, enabled: boolean) {
  return useQuery({ queryKey: ['monitoring', 'teachers', filters], queryFn: () => monitoringApi.teachers(filters), enabled })
}

export function useGroupStats(filters: MonitoringFilters, enabled = true) {
  return useQuery({ queryKey: ['monitoring', 'groups', filters], queryFn: () => monitoringApi.groups(filters), enabled })
}

export function useGroupDetail(id: number | null) {
  return useQuery({ queryKey: ['monitoring', 'group', id], queryFn: () => monitoringApi.group(id as number), enabled: id !== null })
}

export function useTrainerStats(filters: MonitoringFilters, enabled = true) {
  return useQuery({ queryKey: ['monitoring', 'trainers', filters], queryFn: () => monitoringApi.trainers(filters), enabled })
}

export function useTrainerDetail(id: string | null) {
  return useQuery({ queryKey: ['monitoring', 'trainer', id], queryFn: () => monitoringApi.trainer(id as string), enabled: id !== null })
}
