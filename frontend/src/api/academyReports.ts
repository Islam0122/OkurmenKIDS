import { apiClient } from '@/api/client'
import type { AcademyMonthlyReport, CreateAcademyReportResult } from '@/types/academyReport'
import type { Paginated } from '@/types/common'

export interface AcademyReportListParams {
  year?: number
  month?: number
  ordering?: string
  page?: number
}

export const academyReportsApi = {
  /** Admin-only — enforced on the backend (`AcademyMonthlyReportViewSet`), never just hidden in the UI. */
  list: (params?: AcademyReportListParams): Promise<Paginated<AcademyMonthlyReport>> =>
    apiClient.get<Paginated<AcademyMonthlyReport>>('/academy-reports/', { params }).then((r) => r.data),

  get: (id: number): Promise<AcademyMonthlyReport> =>
    apiClient.get<AcademyMonthlyReport>(`/academy-reports/${id}/`).then((r) => r.data),

  /** 201 = a new report was created; 200 = one for this month already
   * existed (the backend never errors on a duplicate month), so the caller
   * can offer "Открыть отчёт" instead of a validation failure. */
  create: (payload: { year: number; month: number }): Promise<CreateAcademyReportResult> =>
    apiClient.post('/academy-reports/', payload).then((r) => ({ created: r.status === 201, report: r.data.report ?? r.data })),

  /** The only field an Admin may ever write on an academy report — every other field is server-computed. */
  updateComment: (id: number, comment: string): Promise<AcademyMonthlyReport> =>
    apiClient.patch<AcademyMonthlyReport>(`/academy-reports/${id}/`, { comment }).then((r) => r.data),

  /** A real backend-rendered A4 PDF (never a screenshot). Fetched as a blob
   * — the endpoint needs the same JWT bearer auth as everything else, so a
   * plain `<a href>` (no Authorization header) would 401. */
  downloadPdf: async (id: number, filename: string): Promise<void> => {
    const response = await apiClient.get(`/academy-reports/${id}/pdf/`, { responseType: 'blob' })
    const url = window.URL.createObjectURL(new Blob([response.data]))
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  },
}
