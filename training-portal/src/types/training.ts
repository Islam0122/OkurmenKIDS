import type { Answer, QuestionOutcome } from './test'

/** An attempt in progress — kept in localStorage so a reload resumes it. */
export interface TrainingProgress {
  attemptId: string
  testId: string
  studentName: string
  /** epoch ms */
  startedAt: number
  /** epoch ms; null = no time limit */
  deadline: number | null
  currentIndex: number
  answers: Record<string, Answer>
  /** questions whose answer was checked (feedback shown, answer locked) */
  checked: Record<string, true>
  visited: Record<string, true>
}

export interface TrainingResult {
  attemptId: string
  testId: string
  testTitle: string
  studentName: string
  startedAt: number
  finishedAt: number
  timedOut: boolean
  total: number
  correct: number
  incorrect: number
  skipped: number
  /** code answers: not auto-graded, left out of the percentage */
  ungraded: number
  /** correct / graded questions · 100, rounded */
  percent: number
  answers: Record<string, Answer>
  outcomes: Record<string, QuestionOutcome>
}

export interface LeaderboardEntry {
  id: string
  name: string
  testId: string
  testTitle: string
  percent: number
  correct: number
  graded: number
  durationSeconds: number
  finishedAt: number
}
