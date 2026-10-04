import { useCallback, useEffect } from 'react'

import * as attemptsApi from '@/api/attempts'
import { postEvent } from '@/api/events'
import { ApiError, NETWORK_ERROR } from '@/api/client'
import { storageService } from '@/services/storageService'

import { useAttemptRunner, type AttemptAdapter } from './useAttemptRunner'

export { isAnswered } from './useAttemptRunner'
export type { NavState, Phase, SaveState } from './useAttemptRunner'

const TRAINING_API: AttemptAdapter = {
  get: attemptsApi.getAttempt,
  save: attemptsApi.saveAnswer,
  check: attemptsApi.checkAnswer,
  submit: (attemptId, token) => attemptsApi.submitAttempt(attemptId, token),
  event: (attemptId, token, eventType, question, beacon) => postEvent(attemptId, token, eventType, question, beacon),
}

/*
 * Training on top of the shared test engine: an attempt started by name,
 * remembered locally ({attemptId, token} only) to resume after a reload.
 */
export function useTraining(testId: string, onFinished: (attemptId: string) => void) {
  const clear = useCallback(() => storageService.clearActiveAttempt(testId), [testId])
  const runner = useAttemptRunner(TRAINING_API, onFinished, clear)
  const { load, setPhase, setError, setBusy, finishedRef, reset } = runner

  // Resume this test's attempt after a reload, else show the intro.
  useEffect(() => {
    finishedRef.current = false
    const saved = storageService.getActiveAttempt(testId)
    if (!saved) { setPhase('intro'); return }
    load(saved, true).catch((err) => {
      if (err instanceof ApiError && err.code === NETWORK_ERROR) { setError(err); setPhase('error'); return }
      storageService.clearActiveAttempt(testId)  // expired token / unknown attempt: start afresh
      setPhase('intro')
    })
  }, [testId, load, setPhase, setError, finishedRef])

  const start = useCallback(async (studentName: string) => {
    setBusy(true)
    setError(null)
    try {
      const started = await attemptsApi.startAttempt(testId, studentName)
      const attemptRef = { attemptId: started.attempt_id, token: started.token }
      storageService.setActiveAttempt(testId, attemptRef)
      storageService.setStudentName(started.student_name)
      finishedRef.current = false
      await load(attemptRef, false)
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError(String(err), 0))
    } finally {
      setBusy(false)
    }
  }, [testId, load, setBusy, setError, finishedRef])

  const restart = useCallback(() => {
    storageService.clearActiveAttempt(testId)
    reset()
  }, [testId, reset])

  return { ...runner, start, restart }
}
