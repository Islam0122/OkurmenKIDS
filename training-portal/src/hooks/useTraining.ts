import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import type { AnswerFeedback, AnswerValue, AttemptState, Question } from '@/types'

import * as attemptsApi from '@/api/attempts'
import { ApiError, NETWORK_ERROR } from '@/api/client'
import { storageService, type AttemptRef } from '@/services/storageService'

/*
 * The training runner for one test, driven by the backend: it starts or
 * resumes the attempt, saves every answer (debounced, retried when the
 * connection is back), asks the backend to check an answer, and submits.
 * Correctness, the score and the deadline are the backend's — nothing is
 * graded here. Only {attemptId, token} is remembered locally, to resume.
 */

export type Phase = 'loading' | 'intro' | 'running' | 'error'
export type SaveState = 'idle' | 'saving' | 'saved' | 'offline'
export type NavState = 'current' | 'answered' | 'unanswered' | 'correct' | 'incorrect'

const SAVE_DELAY_MS = 600

export function isAnswered(value: AnswerValue | null | undefined): boolean {
  return Boolean(value && (value.options.length || value.text.trim()))
}

export function useTraining(testId: string, onFinished: (attemptId: string) => void) {
  const [phase, setPhase] = useState<Phase>('loading')
  const [error, setError] = useState<ApiError | null>(null)
  const [attempt, setAttempt] = useState<AttemptState | null>(null)
  const [answers, setAnswers] = useState<Record<string, AnswerValue>>({})
  const [feedback, setFeedback] = useState<Record<string, AnswerFeedback | true>>({})
  const [index, setIndex] = useState(0)
  const [visited, setVisited] = useState<Record<number, true>>({})
  const [saveState, setSaveState] = useState<SaveState>('idle')
  const [deadline, setDeadline] = useState<number | null>(null)
  const [resumed, setResumed] = useState(false)
  const [busy, setBusy] = useState(false)

  const ref = useRef<AttemptRef | null>(null)
  const pending = useRef<Record<string, AnswerValue>>({})
  const timers = useRef<Record<string, number>>({})
  const finished = useRef(false)
  const finishedCallback = useRef(onFinished)
  finishedCallback.current = onFinished

  const syncDeadline = (seconds: number | null | undefined) => {
    if (seconds === undefined) return
    setDeadline(seconds === null ? null : Date.now() + seconds * 1000)
  }

  const finish = useCallback((attemptId: string) => {
    if (finished.current) return
    finished.current = true
    storageService.clearActiveAttempt(testId)
    finishedCallback.current(attemptId)
  }, [testId])

  const handleError = useCallback((err: unknown) => {
    const apiError = err instanceof ApiError ? err : new ApiError(String(err), 0)
    if (apiError.code === NETWORK_ERROR) { setSaveState('offline'); return }
    if (apiError.status === 409 && apiError.code === 'closed' && ref.current) { finish(ref.current.attemptId); return }
    setError(apiError)
  }, [finish])

  const load = useCallback(async (attemptRef: AttemptRef, isResume: boolean) => {
    const state = await attemptsApi.getAttempt(attemptRef.attemptId, attemptRef.token)
    ref.current = attemptRef
    if (state.status !== 'active') { finish(state.attempt_id); return }
    setAttempt(state)
    setAnswers(Object.fromEntries(state.questions.filter((q) => q.answer).map((q) => [q.id, q.answer as AnswerValue])))
    setFeedback(Object.fromEntries(state.questions.filter((q) => q.checked).map((q) => [q.id, q.feedback ?? true])))
    const firstOpen = state.questions.findIndex((q) => !q.answer)
    setIndex(isResume && firstOpen > 0 ? firstOpen : 0)
    syncDeadline(state.remaining_seconds)
    setResumed(isResume)
    setPhase('running')
  }, [finish])

  // Resume this test's attempt after a reload, else show the intro.
  useEffect(() => {
    finished.current = false
    const saved = storageService.getActiveAttempt(testId)
    if (!saved) { setPhase('intro'); return }
    load(saved, true).catch((err) => {
      if (err instanceof ApiError && err.code === NETWORK_ERROR) { setError(err); setPhase('error'); return }
      storageService.clearActiveAttempt(testId)  // expired token / unknown attempt: start afresh
      setPhase('intro')
    })
  }, [testId, load])

  const start = useCallback(async (studentName: string) => {
    setBusy(true)
    setError(null)
    try {
      const started = await attemptsApi.startAttempt(testId, studentName)
      const attemptRef = { attemptId: started.attempt_id, token: started.token }
      storageService.setActiveAttempt(testId, attemptRef)
      storageService.setStudentName(started.student_name)
      finished.current = false
      await load(attemptRef, false)
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError(String(err), 0))
    } finally {
      setBusy(false)
    }
  }, [testId, load])

  const flushOne = useCallback(async (questionId: string) => {
    const value = pending.current[questionId]
    const attemptRef = ref.current
    if (!value || !attemptRef) return
    window.clearTimeout(timers.current[questionId])
    setSaveState('saving')
    try {
      const saved = await attemptsApi.saveAnswer(attemptRef.attemptId, attemptRef.token, questionId, value)
      if (pending.current[questionId] === value) delete pending.current[questionId]
      syncDeadline(saved.remaining_seconds)
      setSaveState(Object.keys(pending.current).length ? 'saving' : 'saved')
    } catch (err) {
      handleError(err)
      throw err
    }
  }, [handleError])

  const flushAll = useCallback(async () => {
    for (const questionId of Object.keys(pending.current)) await flushOne(questionId)
  }, [flushOne])

  // Answers typed offline go out when the connection is back.
  useEffect(() => {
    const retry = () => { flushAll().catch(() => {}) }
    window.addEventListener('online', retry)
    return () => window.removeEventListener('online', retry)
  }, [flushAll])

  const setAnswer = useCallback((questionId: string, value: AnswerValue) => {
    if (feedback[questionId]) return  // checked answers are locked (the backend refuses them too)
    setAnswers((all) => ({ ...all, [questionId]: value }))
    pending.current[questionId] = value
    setSaveState('saving')
    window.clearTimeout(timers.current[questionId])
    timers.current[questionId] = window.setTimeout(() => { flushOne(questionId).catch(() => {}) }, SAVE_DELAY_MS)
  }, [feedback, flushOne])

  const check = useCallback(async (questionId: string) => {
    const attemptRef = ref.current
    if (!attemptRef) return
    setBusy(true)
    try {
      await flushOne(questionId)
      const result = await attemptsApi.checkAnswer(attemptRef.attemptId, attemptRef.token, questionId)
      setFeedback((all) => ({ ...all, [questionId]: result }))
    } catch (err) {
      handleError(err)
    } finally {
      setBusy(false)
    }
  }, [flushOne, handleError])

  const submit = useCallback(async () => {
    const attemptRef = ref.current
    if (!attemptRef) return
    setBusy(true)
    try {
      await flushAll().catch(() => {})  // what can't be saved is lost; the backend grades what it has
      const result = await attemptsApi.submitAttempt(attemptRef.attemptId, attemptRef.token)
      finish(result.attempt_id)
    } catch (err) {
      handleError(err)
    } finally {
      setBusy(false)
    }
  }, [flushAll, finish, handleError])

  const goTo = useCallback((target: number) => {
    if (!attempt) return
    setVisited((v) => ({ ...v, [index]: true }))
    setIndex(Math.max(0, Math.min(target, attempt.questions.length - 1)))
  }, [attempt, index])

  const navStates = useMemo<NavState[]>(() => (attempt?.questions ?? []).map((q: Question, i) => {
    if (i === index) return 'current'
    const fb = feedback[q.id]
    if (fb && fb !== true && fb.status !== 'pending') return fb.status === 'correct' ? 'correct' : 'incorrect'
    return isAnswered(answers[q.id]) ? 'answered' : 'unanswered'
  }), [attempt, index, feedback, answers])

  const answeredCount = useMemo(
    () => (attempt?.questions ?? []).filter((q) => isAnswered(answers[q.id])).length,
    [attempt, answers],
  )

  const restart = useCallback(() => {
    storageService.clearActiveAttempt(testId)
    ref.current = null
    pending.current = {}
    setAttempt(null)
    setAnswers({})
    setFeedback({})
    setResumed(false)
    setPhase('intro')
  }, [testId])

  return {
    phase, error, attempt, answers, feedback, index, visited, saveState, deadline, resumed, busy,
    navStates, answeredCount, start, setAnswer, check, submit, goTo, restart, clearError: () => setError(null),
  }
}
