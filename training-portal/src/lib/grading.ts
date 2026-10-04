import type { Answer, Question, QuestionOutcome, Test } from '@/types'

/*
 * Answer checking — the rules of the Okurmen Kids testing system
 * (backend apps/testing/services/grading.py):
 *   single / multiple — the chosen set must equal the correct set;
 *   text              — any accepted answer, case- and space-insensitive;
 *   code              — no code runner: not auto-graded («ungraded»).
 */

export function normalizeText(value: string): string {
  return value.trim().replace(/\s+/g, ' ').toLocaleLowerCase()
}

export function isAnswered(answer: Answer | undefined): boolean {
  if (!answer) return false
  return Boolean(answer.options?.length) || Boolean(answer.text?.trim())
}

function asList(value: string | string[] | undefined): string[] {
  if (value === undefined) return []
  return Array.isArray(value) ? value : [value]
}

export function gradeQuestion(question: Question, answer: Answer | undefined): QuestionOutcome {
  if (question.type === 'code') return isAnswered(answer) ? 'ungraded' : 'skipped'
  if (!isAnswered(answer)) return 'skipped'
  const correct = asList(question.correctAnswer)
  if (question.type === 'text') {
    const given = normalizeText(answer?.text ?? '')
    return correct.some((accepted) => normalizeText(accepted) === given) ? 'correct' : 'incorrect'
  }
  const chosen = new Set(answer?.options ?? [])
  if (question.type === 'single' && chosen.size !== 1) return 'incorrect'
  const same = chosen.size === correct.length && correct.every((id) => chosen.has(id))
  return same ? 'correct' : 'incorrect'
}

export interface Score {
  total: number
  correct: number
  incorrect: number
  skipped: number
  ungraded: number
  /** questions that count towards the percentage */
  graded: number
  percent: number
  outcomes: Record<string, QuestionOutcome>
}

export function scoreTest(test: Test, answers: Record<string, Answer>): Score {
  const outcomes: Record<string, QuestionOutcome> = {}
  const tally = { correct: 0, incorrect: 0, skipped: 0, ungraded: 0 }
  for (const question of test.questions) {
    const outcome = gradeQuestion(question, answers[question.id])
    outcomes[question.id] = outcome
    tally[outcome] += 1
  }
  // Code answers can't be checked automatically, so they don't count either way.
  const graded = test.questions.filter((q) => q.type !== 'code').length
  return {
    total: test.questions.length,
    ...tally,
    graded,
    percent: graded ? Math.round((tally.correct / graded) * 100) : 0,
    outcomes,
  }
}

/** Human-readable correct answer (option texts / first accepted text). */
export function correctAnswerText(question: Question): string {
  const correct = asList(question.correctAnswer)
  if (question.type === 'single' || question.type === 'multiple') {
    return (question.options ?? [])
      .filter((option) => correct.includes(option.id))
      .map((option) => option.text)
      .join(', ')
  }
  return correct[0] ?? ''
}
