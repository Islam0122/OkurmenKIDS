import { apiClient } from '@/api/client'
import type { Paginated } from '@/types/common'
import type { ExamListFilter, ExamParticipantResult, ExamParticipantsResponse, ExamSession } from '@/types/exams'

export interface ExamListParams {
  status?: ExamListFilter
  /** Today's sessions plus anything running now (dashboard). */
  today?: boolean
  page?: number
}

/** Read-only: the backend only ever returns sessions of the teacher's own groups. */
export const examsApi = {
  list: ({ status, today, page }: ExamListParams = {}): Promise<Paginated<ExamSession>> =>
    apiClient
      .get<Paginated<ExamSession>>('/teacher/sessions/', {
        params: { status: status && status !== 'all' ? status : undefined, today: today ? 1 : undefined, page },
      })
      .then((r) => r.data),

  get: (id: string): Promise<ExamSession> => apiClient.get<ExamSession>(`/teacher/sessions/${id}/`).then((r) => r.data),

  participants: (id: string): Promise<ExamParticipantsResponse> =>
    apiClient.get<ExamParticipantsResponse>(`/teacher/sessions/${id}/participants/`).then((r) => r.data),

  participantResult: (id: string, participantId: string): Promise<ExamParticipantResult> =>
    apiClient
      .get<ExamParticipantResult>(`/teacher/sessions/${id}/participants/${participantId}/result/`)
      .then((r) => r.data),
}
