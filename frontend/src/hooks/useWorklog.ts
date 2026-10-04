import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { worklogApi } from '@/api/worklog'
import type { EntryListParams, ReportListParams } from '@/api/worklog'
import type { TeamLeadReportInput, WorkLogEntryInput } from '@/types/worklog'

export function useWorklogOptions() {
  return useQuery({ queryKey: ['worklog', 'options'], queryFn: worklogApi.options, staleTime: 5 * 60 * 1000 })
}

export function useWorklogEntries(params: EntryListParams, enabled = true) {
  return useQuery({
    queryKey: ['worklog', 'entries', params],
    queryFn: () => worklogApi.entries(params),
    placeholderData: keepPreviousData,
    enabled,
  })
}

export function useWorklogSummary() {
  return useQuery({ queryKey: ['worklog', 'summary'], queryFn: worklogApi.summary })
}

export function useWorklogReports(params: ReportListParams) {
  return useQuery({
    queryKey: ['worklog', 'reports', params],
    queryFn: () => worklogApi.reports(params),
    placeholderData: keepPreviousData,
  })
}

export function useWorklogReport(id: number | undefined) {
  return useQuery({
    queryKey: ['worklog', 'report', id],
    queryFn: () => worklogApi.report(id as number),
    enabled: id !== undefined,
  })
}

function useInvalidateWorklog() {
  const queryClient = useQueryClient()
  return () => void queryClient.invalidateQueries({ queryKey: ['worklog'] })
}

export function useSaveEntry() {
  const invalidate = useInvalidateWorklog()
  return useMutation({
    mutationFn: ({ id, payload }: { id?: number; payload: WorkLogEntryInput }) =>
      id ? worklogApi.updateEntry(id, payload) : worklogApi.createEntry(payload),
    onSuccess: invalidate,
  })
}

export function useDeleteEntry() {
  const invalidate = useInvalidateWorklog()
  return useMutation({ mutationFn: worklogApi.deleteEntry, onSuccess: invalidate })
}

export function useSaveReport() {
  const invalidate = useInvalidateWorklog()
  return useMutation({
    mutationFn: ({ id, payload }: { id?: number; payload: TeamLeadReportInput }) =>
      id ? worklogApi.updateReport(id, payload) : worklogApi.createReport(payload),
    onSuccess: invalidate,
  })
}

export function useDeleteReport() {
  const invalidate = useInvalidateWorklog()
  return useMutation({ mutationFn: worklogApi.deleteReport, onSuccess: invalidate })
}

export function useRecalculateReport() {
  const invalidate = useInvalidateWorklog()
  return useMutation({ mutationFn: worklogApi.recalculate, onSuccess: invalidate })
}
