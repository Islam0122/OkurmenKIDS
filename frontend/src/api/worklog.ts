import { apiClient } from '@/api/client'
import type { Paginated } from '@/types/common'
import type {
  TeamLeadReport,
  TeamLeadReportInput,
  WorkLogEntry,
  WorkLogEntryInput,
  WorkLogSummary,
  WorklogOptions,
} from '@/types/worklog'

export interface EntryListParams {
  entry_kind?: 'log' | 'task'
  date_from?: string
  date_to?: string
  work_type?: string
  status?: string
  priority?: string
  group?: number
  teacher?: number
  student?: number
  report?: number
  mine?: '1'
  open?: '1'
  search?: string
  ordering?: string
  page?: number
}

export interface ReportListParams {
  kind?: string
  status?: string
  group?: number
  teacher?: number
  student?: number
  mine?: '1'
  page?: number
}

/** Team Lead «Рабочий журнал» (backend: /worklog/…, Team Lead and Admin only;
 * only the author edits a record or report). */
export const worklogApi = {
  options: (): Promise<WorklogOptions> => apiClient.get<WorklogOptions>('/worklog/options/').then((r) => r.data),

  entries: (params?: EntryListParams): Promise<Paginated<WorkLogEntry>> =>
    apiClient.get<Paginated<WorkLogEntry>>('/worklog/entries/', { params }).then((r) => r.data),

  summary: (): Promise<WorkLogSummary> =>
    apiClient.get<WorkLogSummary>('/worklog/entries/summary/').then((r) => r.data),

  createEntry: (payload: WorkLogEntryInput): Promise<WorkLogEntry> =>
    apiClient.post<WorkLogEntry>('/worklog/entries/', payload).then((r) => r.data),

  updateEntry: (id: number, payload: WorkLogEntryInput): Promise<WorkLogEntry> =>
    apiClient.patch<WorkLogEntry>(`/worklog/entries/${id}/`, payload).then((r) => r.data),

  deleteEntry: (id: number): Promise<void> => apiClient.delete(`/worklog/entries/${id}/`).then(() => undefined),

  reports: (params?: ReportListParams): Promise<Paginated<TeamLeadReport>> =>
    apiClient.get<Paginated<TeamLeadReport>>('/worklog/reports/', { params }).then((r) => r.data),

  report: (id: number): Promise<TeamLeadReport> =>
    apiClient.get<TeamLeadReport>(`/worklog/reports/${id}/`).then((r) => r.data),

  createReport: (payload: TeamLeadReportInput): Promise<TeamLeadReport> =>
    apiClient.post<TeamLeadReport>('/worklog/reports/', payload).then((r) => r.data),

  updateReport: (id: number, payload: TeamLeadReportInput): Promise<TeamLeadReport> =>
    apiClient.patch<TeamLeadReport>(`/worklog/reports/${id}/`, payload).then((r) => r.data),

  deleteReport: (id: number): Promise<void> => apiClient.delete(`/worklog/reports/${id}/`).then(() => undefined),

  /** Re-read the LMS figures of the report (author only). */
  recalculate: (id: number): Promise<TeamLeadReport> =>
    apiClient.post<TeamLeadReport>(`/worklog/reports/${id}/recalculate/`).then((r) => r.data),
}
