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

/** A Blob's text (FileReader: works everywhere, incl. older browsers and jsdom). */
function blobText(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(reader.error)
    reader.readAsText(blob)
  })
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

  /** The saved report as a backend-rendered A4 PDF. JWT auth like every
   * call — a plain `<a href>` would 401 — so it is fetched as a blob and
   * saved under the server's file name (teamlead_report_<kind>_<period>.pdf). */
  downloadReportPdf: async (id: number, fallbackName = `teamlead_report_${id}.pdf`): Promise<string> => {
    let response
    try {
      response = await apiClient.get<Blob>(`/worklog/reports/${id}/pdf/`, { responseType: 'blob' })
    } catch (error) {
      // A blob error body hides the API's JSON message — read it back.
      const data = (error as { response?: { data?: unknown } }).response?.data
      if (data instanceof Blob) {
        try {
          const parsed = JSON.parse(await blobText(data)) as { detail?: string }
          if (parsed.detail) (error as { response: { data: unknown } }).response.data = parsed
        } catch {
          // not JSON — keep the original error
        }
      }
      throw error
    }
    const match = /filename="?([^";]+)"?/.exec(String(response.headers['content-disposition'] ?? ''))
    const name = match?.[1] ?? fallbackName
    const href = URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }))
    const link = document.createElement('a')
    link.href = href
    link.download = name.endsWith('.pdf') ? name : `${name}.pdf`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(href)
    return link.download
  },
}
