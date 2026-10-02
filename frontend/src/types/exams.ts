/** Exam sessions of the teacher's groups — `/teacher/sessions/` (apps/testing/teacher_api.py). */

export type SessionPhase = 'draft' | 'scheduled' | 'active' | 'finished' | 'cancelled'

export type ParticipantStatus = 'not_started' | 'in_progress' | 'paused' | 'disconnected' | 'completed' | 'expired'

export interface SessionCounts {
  total: number
  started: number
  /** Includes paused and disconnected students — they are mid-exam. */
  in_progress: number
  disconnected: number
  completed: number
  not_started: number
  expired: number
  average_score: number | null
}

export interface ExamSession {
  id: string
  title: string
  key: string
  session_type: 'exam' | 'training'
  phase: SessionPhase
  phase_label: string
  is_live: boolean
  is_paused: boolean
  test: {
    id: string
    title: string
    level: string
    level_label: string
    passing_score: number
    question_count: number | null
  }
  group: { id: number; name: string } | null
  scheduled_start: string | null
  scheduled_end: string | null
  started_at: string | null
  ends_at: string | null
  time_limit_minutes: number | null
  counts: SessionCounts
}

export interface ExamParticipant {
  id: string
  student: { id: number; name: string }
  status: ParticipantStatus
  status_label: string
  current_question: number
  answered_count: number
  question_total: number
  progress_percent: number
  started_at: string | null
  finished_at: string | null
  last_seen_at: string | null
  duration_seconds: number | null
  /** Only once the student has finished — never while the exam is running. */
  score: number | null
  result_available: boolean
}

export interface ExamParticipantsResponse {
  session: ExamSession
  participants: ExamParticipant[]
  server_time: string
}

export interface ExamResultQuestion {
  number: number
  text: string
  image_url: string | null
  question_type: 'single_choice' | 'multiple_choice' | 'text' | 'code'
  points: number
  status: 'correct' | 'wrong' | 'pending' | 'skipped'
  selected: string[]
  answer_text: string
  correct: string[]
}

export interface ExamParticipantResult {
  student: { id: number; name: string }
  score: number | null
  finished_at: string | null
  duration_seconds: number | null
  passing_score: number
  questions: ExamResultQuestion[]
}

export type ExamListFilter = 'all' | 'live' | 'scheduled' | 'finished'
