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
}
