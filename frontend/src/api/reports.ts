import { apiClient } from '@/api/client'
import type {
  ReportFilterOptions,
  ReportGroupDetail,
  ReportGroupRow,
  ReportOverview,
  ReportPage,
  ReportParams,
  ReportStudentRow,
  ReportSubjectRow,
  ReportTeacherDetail,
  ReportTeacherRow,
} from '@/types/reports'

/** Drops empty values so the backend sees only real filters. */
function clean(params: ReportParams): Record<string, string | number> {
  const out: Record<string, string | number> = {}
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') out[key] = value as string | number
  }
  return out
}

async function download(url: string, params: ReportParams, filename: string): Promise<void> {
  // Same JWT bearer auth as everything else — a plain `<a href>` would 401.
  const response = await apiClient.get(url, { params: clean(params), responseType: 'blob' })
  const disposition = String(response.headers['content-disposition'] ?? '')
  const match = /filename="?([^";]+)"?/.exec(disposition)
  const href = window.URL.createObjectURL(new Blob([response.data]))
  const link = document.createElement('a')
  link.href = href
  link.download = match?.[1] ?? filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.URL.revokeObjectURL(href)
}

/** `/reports/*` — the academy-wide KPI/Reports API. Admin and Team Lead only,
 * enforced on the backend (`IsAdminOrTeamLeadReadOnly`), never just hidden in the UI. */
export const reportsApi = {
  filters: (): Promise<ReportFilterOptions> =>
    apiClient.get<ReportFilterOptions>('/reports/filters/').then((r) => r.data),

  overview: (params: ReportParams): Promise<ReportOverview> =>
    apiClient.get<ReportOverview>('/reports/overview/', { params: clean(params) }).then((r) => r.data),

  teachers: (params: ReportParams): Promise<ReportPage<ReportTeacherRow>> =>
    apiClient.get<ReportPage<ReportTeacherRow>>('/reports/teachers/', { params: clean(params) }).then((r) => r.data),

  teacher: (id: number, params: ReportParams): Promise<ReportTeacherDetail> =>
    apiClient.get<ReportTeacherDetail>(`/reports/teachers/${id}/`, { params: clean(params) }).then((r) => r.data),

  groups: (params: ReportParams): Promise<ReportPage<ReportGroupRow>> =>
    apiClient.get<ReportPage<ReportGroupRow>>('/reports/groups/', { params: clean(params) }).then((r) => r.data),

  group: (id: number, params: ReportParams): Promise<ReportGroupDetail> =>
    apiClient.get<ReportGroupDetail>(`/reports/groups/${id}/`, { params: clean(params) }).then((r) => r.data),

  subjects: (params: ReportParams): Promise<ReportPage<ReportSubjectRow>> =>
    apiClient.get<ReportPage<ReportSubjectRow>>('/reports/subjects/', { params: clean(params) }).then((r) => r.data),

  students: (params: ReportParams): Promise<ReportPage<ReportStudentRow>> =>
    apiClient.get<ReportPage<ReportStudentRow>>('/reports/students/', { params: clean(params) }).then((r) => r.data),

  downloadPdf: (params: ReportParams): Promise<void> => download('/reports/export/pdf/', params, 'report.pdf'),

  downloadExcel: (params: ReportParams): Promise<void> => download('/reports/export/excel/', params, 'report.xlsx'),
}
