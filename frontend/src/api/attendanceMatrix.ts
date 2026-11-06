import { apiClient } from '@/api/client'
import type {
  CellDetail,
  CellUpdate,
  GroupMatrix,
  MatrixMeta,
  MatrixParams,
  MatrixSettings,
  Overview,
  OverviewParams,
} from '@/types/attendanceMatrix'

const BASE = '/attendance-matrix'

function clean<T extends object>(params: T): Record<string, string | number> {
  return Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== '' && v !== null)) as Record<string, string | number>
}

/** Files are behind JWT like every call — a plain `<a href>` would 401 — so they are fetched as a blob. */
async function download(url: string, params: Record<string, string | number>, fallbackName: string): Promise<void> {
  const response = await apiClient.get<Blob>(`${BASE}${url}`, { params, responseType: 'blob' })
  const match = /filename="?([^";]+)"?/.exec(String(response.headers['content-disposition'] ?? ''))
  const href = URL.createObjectURL(response.data)
  const link = document.createElement('a')
  link.href = href
  link.download = match?.[1] ?? fallbackName
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(href)
}

export const attendanceMatrixApi = {
  meta: async () => (await apiClient.get<MatrixMeta>(`${BASE}/meta/`)).data,
  group: async (groupId: number, params: MatrixParams) =>
    (await apiClient.get<GroupMatrix>(`${BASE}/groups/${groupId}/`, { params: clean(params) })).data,
  exportGroup: (groupId: number, params: MatrixParams) =>
    download(`/groups/${groupId}/export/`, clean(params), `attendance_${groupId}.xlsx`),
  cell: async (lesson: number, student: number) =>
    (await apiClient.get<CellDetail>(`${BASE}/cell/`, { params: { lesson, student } })).data,
  updateCell: async (data: CellUpdate) => (await apiClient.put<CellDetail>(`${BASE}/cell/`, data)).data,
  overview: async (params: OverviewParams) =>
    (await apiClient.get<Overview>(`${BASE}/overview/`, { params: clean(params) })).data,
  exportOverview: (params: OverviewParams) => download('/overview/export/', clean(params), 'attendance_overview.xlsx'),
  settings: async () => (await apiClient.get<MatrixSettings>(`${BASE}/settings/`)).data,
  updateSettings: async (data: Partial<MatrixSettings>) => (await apiClient.patch<MatrixSettings>(`${BASE}/settings/`, data)).data,
}
