import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { monitoringApi } from '@/api/monitoring'
import type { MonitoringFilters, ResultBreakdownBy } from '@/types/monitoring'

/** Test Results (finished attempts of LMS students). The backend decides
 * the scope: a Trainer — their own groups; Team Lead / Admin — the academy. */
export function useResults(filters: MonitoringFilters, enabled = true) {
  return useQuery({
    queryKey: ['results', 'list', filters],
    queryFn: () => monitoringApi.results(filters),
    placeholderData: keepPreviousData,
    enabled,
  })
}

export function useResultsSummary(filters: MonitoringFilters, enabled = true) {
  return useQuery({ queryKey: ['results', 'summary', filters], queryFn: () => monitoringApi.resultsSummary(filters), enabled })
}

export function useResultStudents(filters: MonitoringFilters, enabled = true) {
  return useQuery({ queryKey: ['results', 'students', filters], queryFn: () => monitoringApi.resultStudents(filters), enabled })
}

export function useResultBreakdown(filters: MonitoringFilters, by: ResultBreakdownBy, enabled = true) {
  return useQuery({
    queryKey: ['results', 'breakdown', by, filters],
    queryFn: () => monitoringApi.resultBreakdown(filters, by),
    enabled,
  })
}
