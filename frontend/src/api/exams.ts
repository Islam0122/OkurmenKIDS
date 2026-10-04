import { apiClient } from '@/api/client'
import type { Paginated } from '@/types/common'
import type {
  CreateExamSessionPayload,
  ExamListFilter,
  ExamParticipantResult,
  ExamParticipantsResponse,
  ExamSession,
  MyAttempt,
  TestBankItem,
} from '@/types/exams'

export interface ExamListParams {
  status?: ExamListFilter
  /** Today's sessions plus anything running now (dashboard). */
  today?: boolean
  page?: number
  /** Sessions of one group (Admin / Team Lead group page). */
  group?: number
}

/** A Trainer only ever gets sessions of their own groups; Admin / Team Lead
 * get every session and may also create, start and take one (backend-checked). */
export const examsApi = {
  list: ({ status, today, page, group }: ExamListParams = {}): Promise<Paginated<ExamSession>> =>
    apiClient
      .get<Paginated<ExamSession>>('/teacher/sessions/', {
        params: { status: status && status !== 'all' ? status : undefined, today: today ? 1 : undefined, page, group },
      })
      .then((r) => r.data),

  get: (id: string): Promise<ExamSession> => apiClient.get<ExamSession>(`/teacher/sessions/${id}/`).then((r) => r.data),

  participants: (id: string): Promise<ExamParticipantsResponse> =>
    apiClient.get<ExamParticipantsResponse>(`/teacher/sessions/${id}/participants/`).then((r) => r.data),

  participantResult: (id: string, participantId: string): Promise<ExamParticipantResult> =>
    apiClient
      .get<ExamParticipantResult>(`/teacher/sessions/${id}/participants/${participantId}/result/`)
      .then((r) => r.data),

  create: (payload: CreateExamSessionPayload): Promise<ExamSession> =>
    apiClient.post<ExamSession>('/teacher/sessions/', payload).then((r) => r.data),

  start: (id: string): Promise<ExamSession> =>
    apiClient.post<ExamSession>(`/teacher/sessions/${id}/start/`).then((r) => r.data),

  /** Start (or resume) the requesting account's own attempt. */
  take: (id: string): Promise<MyAttempt> => apiClient.post<MyAttempt>(`/teacher/sessions/${id}/take/`).then((r) => r.data),

  myAttempts: (session?: string): Promise<MyAttempt[]> =>
    apiClient.get<MyAttempt[]>('/teacher/my-attempts/', { params: { session } }).then((r) => r.data),

  /** Published tests to create a session from (read-only for a Team Lead). */
  tests: (page = 1): Promise<Paginated<TestBankItem>> =>
    apiClient.get<Paginated<TestBankItem>>('/tests/', { params: { status: 'active', page } }).then((r) => r.data),
}
