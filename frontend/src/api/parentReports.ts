import { apiClient } from '@/api/client'
import type { Paginated } from '@/types/common'
import type {
  ParentReportConfig,
  ParentReportDetail,
  ParentReportListItem,
  ParentReportPreview,
  ParentReportTextUpdate,
} from '@/types/parentReports'

export interface ParentReportListParams {
  group?: number
  report_type?: string
  page?: number
}

/** `student_ids=1&student_ids=2` (Django `getlist`), not axios' default `student_ids[]=`. */
const REPEAT_ARRAYS = { indexes: null }

function saveBlob(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.URL.revokeObjectURL(url)
}

function filenameFrom(disposition: string | undefined, fallback: string): string {
  const match = disposition?.match(/filename="([^"]+)"/)
  return match ? match[1] : fallback
}

export const parentReportsApi = {
  /** Statistics, recommendations and text for the configuration — nothing is stored. */
  preview: (groupId: number, config: ParentReportConfig): Promise<ParentReportPreview> =>
    apiClient
      .get<ParentReportPreview>(`/groups/${groupId}/parent-reports/preview/`, {
        params: config,
        paramsSerializer: REPEAT_ARRAYS,
      })
      .then((r) => r.data),

  /** A new report in the history: snapshot, texts and (for png/both) the PNG pages. */
  generate: (groupId: number, config: ParentReportConfig): Promise<ParentReportDetail> =>
    apiClient.post<ParentReportDetail>(`/groups/${groupId}/parent-reports/generate/`, config).then((r) => r.data),

  list: (params: ParentReportListParams): Promise<Paginated<ParentReportListItem>> =>
    apiClient.get<Paginated<ParentReportListItem>>('/parent-reports/', { params }).then((r) => r.data),

  get: (id: number): Promise<ParentReportDetail> =>
    apiClient.get<ParentReportDetail>(`/parent-reports/${id}/`).then((r) => r.data),

  /** Recalculates the same report from the current data — a new report, the original is kept. */
  regenerate: (id: number): Promise<ParentReportDetail> =>
    apiClient.post<ParentReportDetail>(`/parent-reports/${id}/regenerate/`).then((r) => r.data),

  updateText: (id: number, payload: ParentReportTextUpdate): Promise<ParentReportDetail> =>
    apiClient.post<ParentReportDetail>(`/parent-reports/${id}/text/`, payload).then((r) => r.data),

  /** The message in another language, rendered from the stored snapshot (nothing saved). */
  translatedText: (id: number, payload: ParentReportTextUpdate): Promise<{ text: string }> =>
    apiClient.post<{ text: string }>(`/parent-reports/${id}/text/`, payload).then((r) => r.data),

  /** The PNG as a blob — the endpoint needs the JWT, so a plain `<img src>` would 401. */
  imageBlob: async (id: number, imageId: number): Promise<Blob> => {
    const response = await apiClient.get<Blob>(`/parent-reports/${id}/download/`, {
      params: { image: imageId },
      responseType: 'blob',
    })
    return response.data
  },

  /** One image (`imageId`) or, without it, every page (a ZIP when there are several). */
  download: async (id: number, imageId?: number): Promise<void> => {
    const response = await apiClient.get<Blob>(`/parent-reports/${id}/download/`, {
      params: imageId ? { image: imageId } : undefined,
      responseType: 'blob',
    })
    const fallback = `okurmenkids-report-${id}.${imageId ? 'png' : 'zip'}`
    saveBlob(response.data, filenameFrom(response.headers['content-disposition'] as string | undefined, fallback))
  },
}
