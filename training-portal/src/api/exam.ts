import type { AnswerValue, AttemptResult, AttemptState } from '@/types'

import { apiClient } from './client'
import type { EventResponse } from './events'

/** Exam attempts in the shared test UI — same shapes as the training API;
 * every call carries the attempt's token issued by the student portal. */
const path = (attemptId: string) => `/exam-attempts/${encodeURIComponent(attemptId)}`

export interface ExamState extends AttemptState {
  mode: 'exam'
  paused: boolean
  subject: string
  /** the student portal (cabinet) — where to go after the exam */
  back_url: string
}

export interface ExamResult extends AttemptResult {
  mode: 'exam'
  back_url: string
}

export const getExamAttempt = (attemptId: string, token: string) =>
  apiClient.get<ExamState>(`${path(attemptId)}/`, { token })

/** `seq` — the page's clock when the answer was given: the backend never
 * lets an older save (arriving late, or from another tab) overwrite a newer one. */
export const saveExamAnswer = (attemptId: string, token: string, questionId: string, answer: AnswerValue, seq?: number) =>
  apiClient.put<{ saved: boolean; remaining_seconds: number | null }>(
    `${path(attemptId)}/answers/${encodeURIComponent(questionId)}/`, { ...answer, seq }, { token },
  )

/** The question the student is on — restored after a reload. */
export const saveExamPosition = (attemptId: string, token: string, questionId: string, seq: number) =>
  apiClient.patch<{ saved: boolean; remaining_seconds: number | null }>(
    `${path(attemptId)}/`, { current_question_id: questionId, seq }, { token },
  )

export const postExamEvent = (attemptId: string, token: string, eventType: string, question?: number, keepalive = false) =>
  apiClient.post<EventResponse>(
    `${path(attemptId)}/events/`, { event_type: eventType, metadata: question ? { question } : {} }, { token, keepalive },
  )

export const submitExam = (attemptId: string, token: string, timedOut = false) =>
  apiClient.post<ExamResult>(`${path(attemptId)}/submit/`, { timed_out: timedOut }, { token })

export const getExamResult = (attemptId: string, token: string) =>
  apiClient.get<ExamResult>(`${path(attemptId)}/result/`, { token })
