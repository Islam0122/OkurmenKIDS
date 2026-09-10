import { useQuery } from '@tanstack/react-query'

import { kpiApi, type AnalyticsDashboardParams } from '@/api/kpi'

/** The Analytics Dashboard for a date range (+ optional teacher/group scope) —
 * recomputed from real data on every call, so this key is invalidated
 * wherever Attendance/Homework mutations happen (see useAttendance/useHomework). */
export function useAnalyticsDashboard(params: AnalyticsDashboardParams) {
  return useQuery({
    queryKey: ['kpi', 'dashboard', params],
    queryFn: () => kpiApi.dashboard(params),
  })
}
