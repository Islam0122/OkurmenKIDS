import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import type { Answer, Test, TrainingProgress, TrainingResult } from '@/types'

import { gradeQuestion, isAnswered, scoreTest } from '@/lib/grading'
import { newId } from '@/lib/id'
import { leaderboardService } from '@/services/leaderboardService'
import { trainingService } from '@/services/trainingService'

/*
 * The training engine for one test: start / resume an attempt, answers,
 * «Текшерүү» (check, then the answer is locked), navigation, finish. UI-free
 * — pages render what it returns. The attempt is mirrored to localStorage so
 * a reload continues where the student was.
 */

export type NavState = 'current' | 'answered' | 'unanswered' | 'correct' | 'incorrect'

export function createProgress(test: Test, studentName: string, now = Date.now()): TrainingProgress {
  return {
    attemptId: newId(),
    testId: test.id,
    studentName,
    startedAt: now,
    deadline: test.duration > 0 ? now + test.duration * 60_000 : null,
    currentIndex: 0,
    answers: {},
    checked: {},
    visited: {},
  }
}

export function buildResult(test: Test, progress: TrainingProgress, timedOut: boolean, now = Date.now()): TrainingResult {
  const score = scoreTest(test, progress.answers)
  const finishedAt = timedOut && progress.deadline ? Math.min(now, progress.deadline) : now
  return {
    attemptId: progress.attemptId,
    testId: test.id,
    testTitle: test.title,
    studentName: progress.studentName,
    startedAt: progress.startedAt,
    finishedAt,
    timedOut,
    total: score.total,
    correct: score.correct,
    incorrect: score.incorrect,
    skipped: score.skipped,
    ungraded: score.ungraded,
    percent: score.percent,
    answers: progress.answers,
    outcomes: score.outcomes,
  }
}

export function useTraining(test: Test | null) {
  const [progress, setProgress] = useState<TrainingProgress | null>(() =>
    test ? trainingService.getProgress(test.id) : null,
  )
  const [resumed, setResumed] = useState(() => Boolean(test && trainingService.getProgress(test.id)))

  useEffect(() => {
    if (!test) return
    const saved = trainingService.getProgress(test.id)
    setProgress(saved)
    setResumed(Boolean(saved))
  }, [test])

  // A finished attempt must not be written back as «in progress».
  const finished = useRef(false)
  useEffect(() => {
    if (progress && !finished.current) trainingService.saveProgress(progress)
  }, [progress])

  const start = useCallback((studentName: string) => {
    if (!test) return
    finished.current = false
    setResumed(false)
    setProgress(createProgress(test, studentName))
  }, [test])

  const restart = useCallback(() => {
    if (!test) return
    trainingService.clearProgress(test.id)
    setResumed(false)
    setProgress(null)
  }, [test])

  const update = useCallback((change: (p: TrainingProgress) => TrainingProgress) => {
    setProgress((p) => (p ? change(p) : p))
  }, [])

  const setAnswer = useCallback((questionId: string, answer: Answer) => {
    update((p) => (p.checked[questionId] ? p : { ...p, answers: { ...p.answers, [questionId]: answer } }))
  }, [update])

  const check = useCallback((questionId: string) => {
    update((p) => (isAnswered(p.answers[questionId]) ? { ...p, checked: { ...p.checked, [questionId]: true } } : p))
  }, [update])

  const goTo = useCallback((index: number) => {
    if (!test) return
    update((p) => {
      const target = Math.max(0, Math.min(index, test.questions.length - 1))
      const leaving = test.questions[p.currentIndex]?.id
      return { ...p, currentIndex: target, visited: leaving ? { ...p.visited, [leaving]: true } : p.visited }
    })
  }, [test, update])

  /** Finishes the attempt: result saved, leaderboard updated, progress cleared. */
  const finish = useCallback((timedOut = false): TrainingResult | null => {
    if (!test || !progress) return null
    if (finished.current) return null
    finished.current = true
    const result = buildResult(test, progress, timedOut)
    trainingService.saveResult(result)
    trainingService.clearProgress(test.id)
    void leaderboardService.submitResult(result)
    return result
  }, [test, progress])

  const navStates = useMemo<NavState[]>(() => {
    if (!test || !progress) return []
    return test.questions.map((question, i) => {
      if (i === progress.currentIndex) return 'current'
      const answer = progress.answers[question.id]
      if (progress.checked[question.id] && question.type !== 'code') {
        return gradeQuestion(question, answer) === 'correct' ? 'correct' : 'incorrect'
      }
      return isAnswered(answer) ? 'answered' : 'unanswered'
    })
  }, [test, progress])

  const answeredCount = useMemo(
    () => (test && progress ? test.questions.filter((q) => isAnswered(progress.answers[q.id])).length : 0),
    [test, progress],
  )

  return { progress, resumed, start, restart, setAnswer, check, goTo, finish, navStates, answeredCount }
}
