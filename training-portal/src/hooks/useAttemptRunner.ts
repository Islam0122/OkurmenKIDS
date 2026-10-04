import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import type { AnswerFeedback, AnswerValue, AttemptState, Question } from '@/types'

import type { AttemptResult } from '@/types'

import type { EventResponse } from '@/api/events'
import { ApiError, NETWORK_ERROR } from '@/api/client'
import type { AttemptRef } from '@/services/storageService'

/*
 * The test engine shared by Training and Exam — one runner, driven by the
 * backend: it loads (or restores, after a reload) the attempt, saves every
 * answer (debounced, retried when the connection is back), asks the backend
 * to check an answer (training only) and submits. Correctness, the score and
 * the deadline are the backend's — nothing is graded here; the timer counts
 * down to the server's remaining time, re-synced on every save.
 * The two modes differ only in the API adapter (and the rules behind it).
 */

export type Phase = 'loading' | 'intro' | 'running' | 'error'
export type SaveState = 'idle' | 'saving' | 'saved' | 'offline'
export type NavState = 'current' | 'answered' | 'unanswered' | 'correct' | 'incorrect'

const SAVE_DELAY_MS = 600

export function isAnswered(value: AnswerValue | null | undefined): boolean {
  return Boolean(value && (value.options.length || value.text.trim()))
}

/** How the runner talks to the backend: training or exam endpoints, same shapes. */
export interface AttemptAdapter {
  get: (attemptId: string, token: string) => Promise<AttemptState>
  save: (attemptId: string, token: string, questionId: string, value: AnswerValue) => Promise<{ remaining_seconds: number | null }>
  /** Training only — an exam never shows correctness before it ends. */
  check?: (attemptId: string, token: string, questionId: string) => Promise<AnswerFeedback>
  submit: (attemptId: string, token: string, options: { timedOut: boolean }) => Promise<AttemptResult>
  event: (attemptId: string, token: string, eventType: string, question: number, beacon: boolean) => Promise<EventResponse>
}

export function useAttemptRunner(adapter: AttemptAdapter, onFinished: (attemptId: string) => void, onClosed?: () => void) {
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
  const [tabSwitches, setTabSwitches] = useState(0)

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

  const closedCallback = useRef(onClosed)
  closedCallback.current = onClosed
  const finish = useCallback((attemptId: string) => {
    if (finished.current) return
    finished.current = true
    closedCallback.current?.()
    finishedCallback.current(attemptId)
  }, [])

  const handleError = useCallback((err: unknown) => {
    const apiError = err instanceof ApiError ? err : new ApiError(String(err), 0)
    if (apiError.code === NETWORK_ERROR) { setSaveState('offline'); return }
    if (apiError.status === 409 && apiError.code === 'closed' && ref.current) { finish(ref.current.attemptId); return }
    setError(apiError)
  }, [finish])

  /** `isResume: 'auto'` — a resume when the attempt already has saved answers. */
  const load = useCallback(async (attemptRef: AttemptRef, isResume: boolean | 'auto') => {
    const state = await adapter.get(attemptRef.attemptId, attemptRef.token)
    ref.current = attemptRef
    if (state.status !== 'active') { finish(state.attempt_id); return }
    setAttempt(state)
    setAnswers(Object.fromEntries(state.questions.filter((q) => q.answer).map((q) => [q.id, q.answer as AnswerValue])))
    setFeedback(Object.fromEntries(state.questions.filter((q) => q.checked).map((q) => [q.id, q.feedback ?? true])))
    const resume = isResume === 'auto' ? state.questions.some((q) => q.answer) : isResume
    const firstOpen = state.questions.findIndex((q) => !q.answer)
    setIndex(resume && firstOpen > 0 ? firstOpen : 0)
    syncDeadline(state.remaining_seconds)
    setTabSwitches(state.tab_switch_count)
    setResumed(resume)
    setPhase('running')
  }, [adapter, finish])

  const flushOne = useCallback(async (questionId: string) => {
    const value = pending.current[questionId]
    const attemptRef = ref.current
    if (!value || !attemptRef) return
    window.clearTimeout(timers.current[questionId])
    setSaveState('saving')
    try {
      const saved = await adapter.save(attemptRef.attemptId, attemptRef.token, questionId, value)
      if (pending.current[questionId] === value) delete pending.current[questionId]
      syncDeadline(saved.remaining_seconds)
      setSaveState(Object.keys(pending.current).length ? 'saving' : 'saved')
    } catch (err) {
      handleError(err)
      throw err
    }
  }, [adapter, handleError])

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
    if (!attemptRef || !adapter.check) return
    setBusy(true)
    try {
      await flushOne(questionId)
      const result = await adapter.check(attemptRef.attemptId, attemptRef.token, questionId)
      setFeedback((all) => ({ ...all, [questionId]: result }))
    } catch (err) {
      handleError(err)
    } finally {
      setBusy(false)
    }
  }, [adapter, flushOne, handleError])

  const submit = useCallback(async (timedOut = false) => {
    const attemptRef = ref.current
    if (!attemptRef) return
    setBusy(true)
    try {
      await flushAll().catch(() => {})  // what can't be saved is lost; the backend grades what it has
      const result = await adapter.submit(attemptRef.attemptId, attemptRef.token, { timedOut })
      finish(result.attempt_id)
    } catch (err) {
      handleError(err)
    } finally {
      setBusy(false)
    }
  }, [adapter, flushAll, finish, handleError])

  /** An Exam Mode event → the backend; it may end the attempt (too many tab switches). */
  const reportEvent = useCallback((eventType: string, beacon = false) => {
    const attemptRef = ref.current
    if (!attemptRef || finished.current) return
    adapter.event(attemptRef.attemptId, attemptRef.token, eventType, index + 1, beacon)
      .then((data) => setTabSwitches(data.tab_switch_count))
      .catch((err) => {
        if (err instanceof ApiError && err.status === 409 && (err.code === 'terminated' || err.code === 'closed')) {
          finish(attemptRef.attemptId)
        }
      })
  }, [adapter, finish, index])

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

  const reset = useCallback(() => {
    ref.current = null
    pending.current = {}
    setAttempt(null)
    setAnswers({})
    setFeedback({})
    setResumed(false)
    setPhase('intro')
  }, [])

  return {
    phase, setPhase, error, setError, attempt, answers, feedback, index, visited, saveState, deadline, resumed, busy, setBusy,
    tabSwitches, navStates, answeredCount, load, finishedRef: finished, setAnswer, check, submit, goTo, reset, reportEvent,
    clearError: () => setError(null),
  }
}

export type AttemptRunner = ReturnType<typeof useAttemptRunner>
