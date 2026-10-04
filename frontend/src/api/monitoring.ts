import { apiClient } from '@/api/client'
import type { Paginated } from '@/types/common'
import type {
  GroupDetail,
  GroupStats,
  MonitoringAttempt,
  MonitoringAttemptDetail,
  MonitoringFilterOptions,
  MonitoringFilters,
  MonitoringOverview,
  ResultBreakdownBy,
  ResultBreakdownRow,
  ResultsSummary,
  StudentResultRow,
  TeacherPerformance,
  TrainerDetail,
  TrainerStats,
} from '@/types/monitoring'

/** Empty filters are not sent — the backend ignores unknown values anyway. */
function params(filters: MonitoringFilters): Record<string, string | number> {
  return Object.fromEntries(Object.entries(filters).filter(([, v]) => v !== undefined && v !== '')) as Record<string, string | number>
}

/** Scope (own groups + public trainers of own subjects vs whole academy) is decided by the backend from the JWT. */
export const monitoringApi = {
  overview: (filters: MonitoringFilters) =>
    apiClient.get<MonitoringOverview>('/monitoring/overview/', { params: params(filters) }).then((r) => r.data),
  attempts: (filters: MonitoringFilters) =>
    apiClient.get<Paginated<MonitoringAttempt>>('/monitoring/attempts/', { params: params(filters) }).then((r) => r.data),
  attempt: (id: string) => apiClient.get<MonitoringAttemptDetail>(`/monitoring/attempts/${id}/`).then((r) => r.data),
  teachers: (filters: MonitoringFilters) =>
    apiClient.get<TeacherPerformance[]>('/monitoring/teachers/', { params: params(filters) }).then((r) => r.data),
  groups: (filters: MonitoringFilters) =>
    apiClient.get<GroupStats[]>('/monitoring/groups/', { params: params(filters) }).then((r) => r.data),
  group: (id: number) => apiClient.get<GroupDetail>(`/monitoring/groups/${id}/`).then((r) => r.data),
  trainers: (filters: MonitoringFilters) =>
    apiClient.get<TrainerStats[]>('/monitoring/trainers/', { params: params(filters) }).then((r) => r.data),
  trainer: (id: string) => apiClient.get<TrainerDetail>(`/monitoring/trainers/${id}/`).then((r) => r.data),
  filters: () => apiClient.get<MonitoringFilterOptions>('/monitoring/filters/').then((r) => r.data),

  // Test Results — finished attempts of LMS students, same scope and filters.
  results: (filters: MonitoringFilters) =>
    apiClient.get<Paginated<MonitoringAttempt>>('/monitoring/results/', { params: params(filters) }).then((r) => r.data),
  resultsSummary: (filters: MonitoringFilters) =>
    apiClient.get<ResultsSummary>('/monitoring/results/summary/', { params: params(filters) }).then((r) => r.data),
  resultStudents: (filters: MonitoringFilters) =>
    apiClient.get<StudentResultRow[]>('/monitoring/results/students/', { params: params(filters) }).then((r) => r.data),
  resultBreakdown: (filters: MonitoringFilters, by: ResultBreakdownBy) =>
    apiClient.get<ResultBreakdownRow[]>('/monitoring/results/breakdown/', { params: { ...params(filters), by } }).then((r) => r.data),
  /** Excel of the filtered results — downloaded as a file. */
  exportResults: async (filters: MonitoringFilters) => {
    const response = await apiClient.get<Blob>('/monitoring/results/export/', { params: params(filters), responseType: 'blob' })
    const disposition = String(response.headers['content-disposition'] ?? '')
    const name = /filename="?([^";]+)"?/.exec(disposition)?.[1] ?? 'test-results.xlsx'
    const url = URL.createObjectURL(response.data)
    const link = document.createElement('a')
    link.href = url
    link.download = name
    link.click()
    URL.revokeObjectURL(url)
  },
}
