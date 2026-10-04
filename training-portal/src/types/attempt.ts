import type { Question } from './question'
import type { SecuritySettings } from './test'

/** POST /api/v1/training/attempts/ (+ token) and the summary part of others */
export interface AttemptSummary {
  attempt_id: string
  test_id: string
  test_title: string
  student_name: string
  started_at: string
  /** null — no time limit */
  expires_at: string | null
}

export interface StartedAttempt extends AttemptSummary {
  token: string
}

/** GET /api/v1/training/attempts/<id>/ */
export interface AttemptState extends AttemptSummary {
  status: 'active' | 'finished' | 'expired'
  remaining_seconds: number | null
  show_explanation: boolean
  security: SecuritySettings
  tab_switch_count: number
  violation_count: number
  questions: Question[]
}

export interface ReviewRow {
  number: number
  question_id: string
  type: Question['type']
  text: string
  status: 'correct' | 'wrong' | 'pending' | 'skipped'
  selected: string[]
  answer_text: string
  correct: string[]
  explanation: string
}

/** POST …/submit/ and GET …/result/ — computed by the backend. */
export interface AttemptResult extends AttemptSummary {
  status: 'completed' | 'active' | 'expired'
  finish_reason: '' | 'submitted' | 'time_expired' | 'session_closed' | 'violations'
  finished_at: string | null
  duration_seconds: number | null
  show_result: boolean
  passing_score: number
  /* present when the test shows results */
  score?: number
  max_score?: number
  percentage?: number
  total?: number
  correct?: number
  incorrect?: number
  skipped?: number
  pending?: number
  passed?: boolean | null
  review?: ReviewRow[]
}
