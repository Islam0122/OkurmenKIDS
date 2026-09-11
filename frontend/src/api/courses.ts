import { apiClient } from '@/api/client'
import type { Course, CourseLessonPlan } from '@/types/academy'
import type { Paginated } from '@/types/common'

export interface CourseListParams {
  search?: string
  subject?: number
  ordering?: string
  page?: number
}

export const coursesApi = {
  list: (params?: CourseListParams): Promise<Paginated<Course>> =>
    apiClient.get<Paginated<Course>>('/courses/', { params }).then((r) => r.data),

  get: (id: number): Promise<Course> => apiClient.get<Course>(`/courses/${id}/`).then((r) => r.data),

  lessonPlans: (id: number): Promise<CourseLessonPlan[]> =>
    apiClient.get<CourseLessonPlan[]>(`/courses/${id}/lesson-plans/`).then((r) => r.data),
}
