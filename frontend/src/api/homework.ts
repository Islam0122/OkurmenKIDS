import { apiClient } from '@/api/client'
import type { BulkHomeworkResultItem, Homework, HomeworkResult, HomeworkResultStatus } from '@/types/homework'
import type { Paginated } from '@/types/common'

export interface HomeworkListParams {
  lesson?: number
  group?: number
  search?: string
  ordering?: string
  page?: number
}

export const homeworkApi = {
  list: (params?: HomeworkListParams): Promise<Paginated<Homework>> =>
    apiClient.get<Paginated<Homework>>('/academy/homeworks/', { params }).then((r) => r.data),

  get: (id: number): Promise<Homework> => apiClient.get<Homework>(`/academy/homeworks/${id}/`).then((r) => r.data),

  /** Every active student of the lesson's group, with their current result (or a `not_submitted` placeholder). */
  getResultsRoster: (id: number): Promise<HomeworkResult[]> =>
    apiClient.get<HomeworkResult[]>(`/academy/homeworks/${id}/results/`).then((r) => r.data),

  /** Bulk-grade the given students in one call. */
  saveResults: (id: number, items: BulkHomeworkResultItem[]): Promise<HomeworkResult[]> =>
    apiClient.post<HomeworkResult[]>(`/academy/homeworks/${id}/results/`, items).then((r) => r.data),
}

export interface HomeworkResultListParams {
  homework?: number
  student?: number
  status?: HomeworkResultStatus
  ordering?: string
  page?: number
}

export const homeworkResultsApi = {
  /** Direct CRUD listing — e.g. a single student's homework history. */
  list: (params?: HomeworkResultListParams): Promise<Paginated<HomeworkResult>> =>
    apiClient.get<Paginated<HomeworkResult>>('/academy/homework-results/', { params }).then((r) => r.data),
}
