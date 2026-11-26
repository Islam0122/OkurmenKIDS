import { apiClient } from '@/api/client'
import type { Paginated } from '@/types/common'
import type {
  AttendanceMark,
  ConflictCheck,
  ParallelAnalytics,
  ParallelOptions,
  ParallelSession,
  RosterGroup,
  SessionHistoryEntry,
  SessionHomework,
  SessionInput,
  SessionListParams,
  SessionStatistics,
} from '@/types/parallelLessons'

/** /api/v1/parallel-lessons/ — apps.academy.parallel_session_views. */
const BASE = '/parallel-lessons'
const data = <T>(promise: Promise<{ data: T }>) => promise.then((r) => r.data)

export const parallelLessonsApi = {
  list: (params: SessionListParams) => data(apiClient.get<Paginated<ParallelSession>>(`${BASE}/`, { params })),
  get: (id: number) => data(apiClient.get<ParallelSession>(`${BASE}/${id}/`)),
  options: () => data(apiClient.get<ParallelOptions>(`${BASE}/options/`)),
  create: (body: SessionInput) => data(apiClient.post<ParallelSession>(`${BASE}/`, body)),
  update: (id: number, body: Partial<SessionInput>) => data(apiClient.patch<ParallelSession>(`${BASE}/${id}/`, body)),
  check: (body: Partial<SessionInput> & { session?: number }) => data(apiClient.post<ConflictCheck>(`${BASE}/check/`, body)),
  cancel: (id: number, reason: string) => data(apiClient.post<ParallelSession>(`${BASE}/${id}/cancel/`, { reason })),
  start: (id: number) => data(apiClient.post<ParallelSession>(`${BASE}/${id}/start/`)),
  complete: (id: number) => data(apiClient.post<ParallelSession>(`${BASE}/${id}/complete/`)),
  addGroup: (id: number, group: number) => data(apiClient.post<ParallelSession>(`${BASE}/${id}/groups/`, { group })),
  removeGroup: (id: number, group: number, reason = '') =>
    data(apiClient.delete<ParallelSession>(`${BASE}/${id}/groups/${group}/`, { data: { reason } })),
  roster: (id: number) => data(apiClient.get<RosterGroup[]>(`${BASE}/${id}/attendance/`)),
  markAttendance: (id: number, group: number, entries: { student: number; status: AttendanceMark; comment?: string }[]) =>
    data(apiClient.post<{ roster: RosterGroup[] }>(`${BASE}/${id}/attendance/`, { group, entries })),
  homework: (id: number) => data(apiClient.get<SessionHomework[]>(`${BASE}/${id}/homework/`)),
  addHomework: (id: number, body: { title: string; description?: string; deadline?: string | null; groups?: number[] }) =>
    data(apiClient.post<SessionHomework[]>(`${BASE}/${id}/homework/`, body)),
  statistics: (id: number) => data(apiClient.get<SessionStatistics>(`${BASE}/${id}/statistics/`)),
  history: (id: number) => data(apiClient.get<SessionHistoryEntry[]>(`${BASE}/${id}/history/`)),
  analytics: (params: { start: string; end: string; teacher?: number }) =>
    data(apiClient.get<ParallelAnalytics>(`${BASE}/analytics/`, { params })),
}
