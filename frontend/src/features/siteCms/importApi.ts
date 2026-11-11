import { apiClient } from '@/api/client'
import type { Paginated } from '@/types/common'

/** Массовое заполнение контента — backend apps.website.content_import,
 * /api/v1/marketing/site/import/. The server reads and validates the file,
 * keeps the validated rows and imports only those (never what the browser
 * sends); imported records stay unpublished. */
const BASE = '/marketing/site/import'

export type ImportKind = 'events' | 'achievements' | 'news'
export const KIND_LABEL: Record<ImportKind, string> = { events: 'Мероприятия', achievements: 'Достижения', news: 'Новости' }
export const KINDS: ImportKind[] = ['events', 'achievements', 'news']

export interface RowMessage {
  field: string
  message: string
}

export interface ImportRow {
  key: string
  kind: ImportKind
  row: number
  title: string
  category: string
  category_raw: string
  date: string
  languages: { ru: boolean; ky: boolean; en: boolean }
  status: string
  status_raw: string
  cover: string
  verification_note: string
  errors: RowMessage[]
  warnings: RowMessage[]
  duplicate: { id: number; title: string; slug: string; status: string; status_label: string; updatable: boolean } | null
  valid: boolean
}

export interface RowResult {
  result: 'created' | 'updated' | 'skipped' | 'failed'
  message: string
  object_id?: number
  kind: ImportKind
  row: number
  title: string
  verification_note: string
}

export interface BatchSummary {
  id: number
  file_name: string
  file_size: number
  created_by_name: string
  content_type: ImportKind | 'mixed'
  content_type_label: string
  status: 'preview' | 'importing' | 'completed' | 'partial' | 'failed' | 'cancelled'
  status_label: string
  total_rows: number
  selected_rows: number
  imported_count: number
  created_count: number
  updated_count: number
  skipped_count: number
  failed_count: number
  error_rows: number
  created_at: string
  finished_at: string | null
}

export interface Batch extends BatchSummary {
  sheets: Partial<Record<ImportKind, number>>
  rows: ImportRow[]
  results: Record<string, RowResult>
}

async function download(url: string, params: Record<string, string>, fallback: string) {
  const response = await apiClient.get<Blob>(url, { params, responseType: 'blob' })
  const match = /filename="([^"]+)"/.exec(String(response.headers['content-disposition'] ?? ''))
  const href = window.URL.createObjectURL(response.data)
  const link = document.createElement('a')
  link.href = href
  link.download = match?.[1] ?? fallback
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.URL.revokeObjectURL(href)
}

export const importApi = {
  preview: (file: File, opts: { type?: ImportKind; types?: ImportKind[] }) => {
    const form = new FormData()
    form.append('file', file)
    if (opts.type) form.append('type', opts.type)
    if (opts.types?.length) form.append('types', opts.types.join(','))
    return apiClient.post<Batch>(`${BASE}/preview/`, form).then((r) => r.data)
  },
  commit: (id: number, body: { rows: string[]; update: string[]; confirm_update: boolean; finalize: boolean }) =>
    apiClient.post<Batch>(`${BASE}/${id}/commit/`, body).then((r) => r.data),
  cancel: (id: number) => apiClient.post(`${BASE}/${id}/cancel/`).then(() => undefined),
  history: (page: number) => apiClient.get<Paginated<BatchSummary>>(`${BASE}/`, { params: { page } }).then((r) => r.data),
  batch: (id: number) => apiClient.get<Batch>(`${BASE}/${id}/`).then((r) => r.data),
  downloadTemplate: (format: 'xlsx' | 'csv', type?: ImportKind) =>
    download(`${BASE}/template/`, { file_format: format, ...(type ? { type } : {}) }, format === 'xlsx' ? 'okurmen-content-template.xlsx' : `okurmen-${type}-template.csv`),
  downloadErrors: (id: number) => download(`${BASE}/${id}/errors/`, {}, `import-${id}-errors.csv`),
}

/** Rows imported per request: the progress bar moves with real server work. */
export const CHUNK = 20
export const MAX_FILE_BYTES = 5 * 1024 * 1024
