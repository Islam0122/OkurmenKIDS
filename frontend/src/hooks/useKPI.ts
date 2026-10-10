import { useQuery } from '@tanstack/react-query'

import { groupsApi } from '@/api/groups'
import { kpiApi, type AnalyticsDashboardParams } from '@/api/kpi'
import type { StudentProgressParams } from '@/types/studentProgress'

/** The Analytics Dashboard for a date range (+ optional teacher/group scope) —
 * recomputed from real data on every call, so this key is invalidated
 * wherever Attendance/Homework mutations happen (see useAttendance/useHomework). */
export function useAnalyticsDashboard(params: AnalyticsDashboardParams) {
  return useQuery({
    queryKey: ['kpi', 'dashboard', params],
    queryFn: () => kpiApi.dashboard(params),
  })
}

/** «Прогресс студентов» of a group for the KPI period. Under the `kpi` key, so
 * every attendance / homework change that refreshes the KPI refreshes it too. */
export function useGroupStudentProgress(groupId: number, params: StudentProgressParams) {
  return useQuery({
    queryKey: ['kpi', 'student-progress', groupId, params],
    queryFn: () => groupsApi.studentProgress(groupId, params),
  })
}

/** One student's lessons / homework / tests of that period — loaded when the row is opened. */
export function useStudentProgressDetail(groupId: number, studentId: number, params: StudentProgressParams) {
  return useQuery({
    queryKey: ['kpi', 'student-progress', groupId, params, studentId],
    queryFn: () => groupsApi.studentProgressDetail(groupId, studentId, params),
  })
}
