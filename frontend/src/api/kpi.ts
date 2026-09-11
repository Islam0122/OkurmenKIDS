import { apiClient } from '@/api/client'
import type { AnalyticsDashboard, KPICompareMode, KPIPeriodKey } from '@/types/kpi'

/** `period`/date range + optional comparison + optional filters — every
 * field but `period` is optional. A Teacher's own scoping happens
 * server-side regardless of what's passed here (see `AnalyticsDashboardView`). */
export interface AnalyticsDashboardParams {
  period: KPIPeriodKey
  start_date?: string
  end_date?: string
  /** "true" (shorthand for previous_period), a named KPICompareMode, or
   * omitted entirely for no comparison. */
  compare?: KPICompareMode | 'true'
  compare_start_date?: string
  compare_end_date?: string
  teacher?: number
  group?: number
  course?: number
  subject?: number
}

export const kpiApi = {
  /** `GET /academy/analytics/dashboard/` — computed fresh on every call, nothing cached server-side. */
  dashboard: (params: AnalyticsDashboardParams): Promise<AnalyticsDashboard> =>
    apiClient.get<AnalyticsDashboard>('/academy/analytics/dashboard/', { params }).then((r) => r.data),
}
