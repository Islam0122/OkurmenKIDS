import { apiClient } from '@/api/client'
import type { Paginated } from '@/types/common'
import type {
  Campaign,
  CampaignInput,
  ContentInput,
  ContentItem,
  ContentParams,
  MarketingDashboard,
  MarketingMeta,
  MarketingReport,
  MarketingTask,
  ReportPeriod,
  TaskInput,
  TasksParams,
} from '@/types/marketing'

const BASE = '/marketing'

/** Кабинет маркетинга (backend: apps.marketing). Все права проверяет сервер. */
export const marketingApi = {
  meta: () => apiClient.get<MarketingMeta>(`${BASE}/meta/`).then((r) => r.data),
  dashboard: (params: { date_from?: string; date_to?: string }) =>
    apiClient.get<MarketingDashboard>(`${BASE}/dashboard/`, { params }).then((r) => r.data),
  report: (params: { period: ReportPeriod; date?: string }) =>
    apiClient.get<MarketingReport>(`${BASE}/reports/`, { params }).then((r) => r.data),

  content: (params: ContentParams) => apiClient.get<Paginated<ContentItem>>(`${BASE}/content/`, { params }).then((r) => r.data),
  createContent: (body: ContentInput) => apiClient.post<ContentItem>(`${BASE}/content/`, body).then((r) => r.data),
  updateContent: (id: number, body: Partial<ContentInput>) => apiClient.patch<ContentItem>(`${BASE}/content/${id}/`, body).then((r) => r.data),
  deleteContent: (id: number) => apiClient.delete(`${BASE}/content/${id}/`).then(() => undefined),

  tasks: (params: TasksParams) => apiClient.get<Paginated<MarketingTask>>(`${BASE}/tasks/`, { params }).then((r) => r.data),
  createTask: (body: TaskInput) => apiClient.post<MarketingTask>(`${BASE}/tasks/`, body).then((r) => r.data),
  updateTask: (id: number, body: Partial<TaskInput>) => apiClient.patch<MarketingTask>(`${BASE}/tasks/${id}/`, body).then((r) => r.data),
  deleteTask: (id: number) => apiClient.delete(`${BASE}/tasks/${id}/`).then(() => undefined),

  campaigns: (params: { status?: string; page?: number; page_size?: number }) =>
    apiClient.get<Paginated<Campaign>>(`${BASE}/campaigns/`, { params }).then((r) => r.data),
  saveCampaign: (id: number | null, body: CampaignInput) =>
    (id === null ? apiClient.post<Campaign>(`${BASE}/campaigns/`, body) : apiClient.patch<Campaign>(`${BASE}/campaigns/${id}/`, body)).then((r) => r.data),
  deleteCampaign: (id: number) => apiClient.delete(`${BASE}/campaigns/${id}/`).then(() => undefined),
}
