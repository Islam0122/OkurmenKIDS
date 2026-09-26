import { apiClient } from '@/api/client'
import type { Paginated } from '@/types/common'
import type {
  RequiredFeedbackResponse,
  ScholarshipAnalytics,
  ScholarshipEvaluation,
  ScholarshipPeriod,
  TrainerFeedback,
  TrainerFeedbackInput,
} from '@/types/scholarship'

export const scholarshipsApi = {
  /** Admin gets full rows; a Teacher only dates/status (`ScholarshipPeriodViewSet.get_serializer_class`). */
  periods: (): Promise<Paginated<ScholarshipPeriod>> =>
    apiClient.get<Paginated<ScholarshipPeriod>>('/scholarship-periods/').then((r) => r.data),

  /** Admin only. */
  ranking: (periodId: number, page = 1): Promise<Paginated<ScholarshipEvaluation>> =>
    apiClient
      .get<Paginated<ScholarshipEvaluation>>(`/scholarship-periods/${periodId}/ranking/`, { params: { page } })
      .then((r) => r.data),

  /** Admin only. */
  analytics: (periodId: number): Promise<ScholarshipAnalytics> =>
    apiClient.get<ScholarshipAnalytics>(`/scholarship-periods/${periodId}/analytics/`).then((r) => r.data),

  recalculate: (periodId: number): Promise<ScholarshipPeriod> =>
    apiClient.post<ScholarshipPeriod>(`/scholarship-periods/${periodId}/recalculate/`).then((r) => r.data),

  approve: (periodId: number): Promise<ScholarshipPeriod> =>
    apiClient.post<ScholarshipPeriod>(`/scholarship-periods/${periodId}/approve/`).then((r) => r.data),

  /** Teacher only: every student/subject they taught in the period, with their feedback if given. */
  requiredFeedback: (periodId: number): Promise<RequiredFeedbackResponse> =>
    apiClient
      .get<RequiredFeedbackResponse>('/scholarship-feedback/required/', { params: { period: periodId } })
      .then((r) => r.data),

  createFeedback: (
    payload: TrainerFeedbackInput & { period: number; student: number; subject: number },
  ): Promise<TrainerFeedback> => apiClient.post<TrainerFeedback>('/scholarship-feedback/', payload).then((r) => r.data),

  updateFeedback: (id: number, payload: TrainerFeedbackInput): Promise<TrainerFeedback> =>
    apiClient.patch<TrainerFeedback>(`/scholarship-feedback/${id}/`, payload).then((r) => r.data),
}
