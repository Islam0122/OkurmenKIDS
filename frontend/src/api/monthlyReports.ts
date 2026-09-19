import { apiClient } from '@/api/client'
import type { CreateMonthlyReportResult, MonthlyTeacherReport } from '@/types/monthlyReport'
import type { Paginated } from '@/types/common'

export interface MonthlyReportListParams {
  year?: number
  month?: number
  teacher?: number
  ordering?: string
  page?: number
}

export const monthlyReportsApi = {
  /** A Teacher sees only their own reports; Admin sees every teacher's (see `MonthlyTeacherReportViewSet.get_queryset`). */
  list: (params?: MonthlyReportListParams): Promise<Paginated<MonthlyTeacherReport>> =>
    apiClient.get<Paginated<MonthlyTeacherReport>>('/monthly-reports/', { params }).then((r) => r.data),

  get: (id: number): Promise<MonthlyTeacherReport> =>
    apiClient.get<MonthlyTeacherReport>(`/monthly-reports/${id}/`).then((r) => r.data),

  /** 201 = a new report was created; 200 = one for this month already
   * existed (the backend never errors on a duplicate month — see
   * `MonthlyTeacherReportViewSet.create`), so the caller can offer
   * "Открыть отчёт" instead of a validation failure. */
  create: (payload: { year: number; month: number }): Promise<CreateMonthlyReportResult> =>
    apiClient.post('/monthly-reports/', payload).then((r) => ({ created: r.status === 201, report: r.data.report ?? r.data })),

  /** The only field a Teacher may ever write on their own report — every other field is server-computed. */
  updateComment: (id: number, comment: string): Promise<MonthlyTeacherReport> =>
    apiClient.patch<MonthlyTeacherReport>(`/monthly-reports/${id}/`, { comment }).then((r) => r.data),

  /** A real backend-rendered PDF (never a screenshot). Fetched as a blob —
   * the endpoint needs the same JWT bearer auth as everything else, so a
   * plain `<a href>` (no Authorization header) would 401. */
  downloadPdf: async (id: number, filename: string): Promise<void> => {
    const response = await apiClient.get(`/monthly-reports/${id}/pdf/`, { responseType: 'blob' })
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
