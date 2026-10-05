import { useEffect, useState } from 'react'

import * as examApi from '@/api/exam'
import { ApiError } from '@/api/client'

import { useAttemptRunner, type AttemptAdapter } from './useAttemptRunner'

const EXAM_API: AttemptAdapter = {
  get: examApi.getExamAttempt,
  save: examApi.saveExamAnswer,
  position: examApi.saveExamPosition,
  submit: (attemptId, token, { timedOut }) => examApi.submitExam(attemptId, token, timedOut),
  event: (attemptId, token, eventType, question, beacon) => examApi.postExamEvent(attemptId, token, eventType, question, beacon),
}

const tokenKey = (attemptId: string) => `okurmen_exam_${attemptId}`

/**
 * The attempt's token: from the link the session-key page (/exam/?key=…)
 * redirects to (`#t=…`, read once and
 * removed from the address bar), then kept for this browser tab only
 * (sessionStorage) so a reload restores the same attempt.
 */
export function examToken(attemptId: string): string | null {
  const fromLink = new URLSearchParams(window.location.hash.slice(1)).get('t')
  try {
    if (fromLink) {
      window.sessionStorage.setItem(tokenKey(attemptId), fromLink)
      window.history.replaceState(null, '', window.location.pathname + window.location.search)
      return fromLink
    }
    return window.sessionStorage.getItem(tokenKey(attemptId))
  } catch {
    return fromLink
  }
}

/** Exam on top of the shared test engine: the attempt already exists (started
 * by the backend's session-key page) — it is only restored, never started here. */
export function useExam(attemptId: string, onFinished: (attemptId: string) => void) {
  const runner = useAttemptRunner(EXAM_API, onFinished)
  const { load, setPhase, setError } = runner
  const [token] = useState(() => examToken(attemptId))

  useEffect(() => {
    if (!token) { setError(new ApiError('', 403, 'forbidden')); setPhase('error'); return }
    load({ attemptId, token }, 'auto').catch((err) => {
      setError(err instanceof ApiError ? err : new ApiError(String(err), 0))
      setPhase('error')
    })
  }, [attemptId, token, load, setPhase, setError])

  return { ...runner, token }
}
