import type { AnswerFeedback, AnswerValue, AttemptResult, AttemptState, StartedAttempt } from '@/types'

import { apiClient } from './client'

const path = (attemptId: string) => `/attempts/${encodeURIComponent(attemptId)}`

export const startAttempt = (testId: string, studentName: string) =>
  apiClient.post<StartedAttempt>('/attempts/', { test_id: testId, student_name: studentName })

export const getAttempt = (attemptId: string, token: string) =>
  apiClient.get<AttemptState>(`${path(attemptId)}/`, { token })

export const saveAnswer = (attemptId: string, token: string, questionId: string, answer: AnswerValue) =>
  apiClient.put<{ saved: boolean; remaining_seconds: number | null }>(
    `${path(attemptId)}/answers/${encodeURIComponent(questionId)}/`, answer, { token },
  )

export const checkAnswer = (attemptId: string, token: string, questionId: string) =>
  apiClient.post<AnswerFeedback>(`${path(attemptId)}/answers/${encodeURIComponent(questionId)}/check/`, {}, { token })

export const submitAttempt = (attemptId: string, token: string) =>
  apiClient.post<AttemptResult>(`${path(attemptId)}/submit/`, {}, { token })

export const getResult = (attemptId: string) => apiClient.get<AttemptResult>(`${path(attemptId)}/result/`)
