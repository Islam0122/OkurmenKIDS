import { apiClient } from '@/api/client'
import type { AnalyticsDashboard } from '@/types/kpi'

/** Every field but the date range is optional — omit `teacher`/`group` for
 * "all of them". A Teacher's own scoping happens server-side regardless of
 * what's passed here (see `AnalyticsDashboardView`). */
export interface AnalyticsDashboardParams {
  date_from: string
  date_to: string
  teacher?: number
  group?: number
}

export const kpiApi = {
  /** `GET /academy/analytics/dashboard/` — computed fresh on every call, nothing cached server-side. */
  dashboard: (params: AnalyticsDashboardParams): Promise<AnalyticsDashboard> =>
    apiClient.get<AnalyticsDashboard>('/academy/analytics/dashboard/', { params }).then((r) => r.data),
}
