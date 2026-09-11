import { apiClient } from '@/api/client'
import type { Group, GroupSchedule, GroupStatus, LessonStatus, Student } from '@/types/academy'
import type { Paginated } from '@/types/common'

export interface GroupListParams {
  search?: string
  course?: number
  teacher?: number
  room?: number
  status?: GroupStatus
  ordering?: string
  page?: number
}

export const groupsApi = {
  list: (params?: GroupListParams): Promise<Paginated<Group>> =>
    apiClient.get<Paginated<Group>>('/groups/', { params }).then((r) => r.data),

  get: (id: number): Promise<Group> => apiClient.get<Group>(`/groups/${id}/`).then((r) => r.data),

  /** The group's own recurring pattern plus every dated Lesson it has — the
   * "Пн/Чт/Пт по дням" schedule view, not a flat Lesson list. */
  schedule: (id: number, params?: { status?: LessonStatus }): Promise<GroupSchedule> =>
    apiClient.get<GroupSchedule>(`/groups/${id}/schedule/`, { params }).then((r) => r.data),

  /** The group's active students (or all, with `is_active: false`). */
  students: (id: number, params?: { is_active?: boolean }): Promise<Student[]> =>
    apiClient.get<Student[]>(`/groups/${id}/students/`, { params }).then((r) => r.data),
}
