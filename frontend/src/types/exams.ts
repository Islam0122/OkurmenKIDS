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
  subject: string | null
  /** The trainer the session belongs to, if any. */
  teacher_name: string | null
  /** The LMS account that created it through the LMS (e.g. the Team Lead). */
  created_by_name: string | null
  /** Backend decides: Admin — any created session; Team Lead — one they created. */
  can_start: boolean
  /** Admin / Team Lead may take the test themselves. */
  can_take: boolean
  max_attempts: number | null
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
  /** Exam Mode (student portal): tab switches / all violations of the attempt. */
  tab_switch_count: number
  violation_count: number
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

/** `POST /teacher/sessions/` — the same rules as the admin's «Создание сессии». */
export interface CreateExamSessionPayload {
  test: string
  group: number
  /** YYYY-MM-DD */
  date: string
  /** HH:MM */
  start_time: string
  /** HH:MM — optional: defaults to the test's time limit (else 60 min). */
  end_time?: string
  title?: string
}

/** One of the requesting account's own attempts (`/teacher/my-attempts/`, `/take/`). */
export interface MyAttempt {
  id: string
  session: { id: string; title: string; group: { id: number; name: string } | null }
  test: { id: string; title: string; passing_score: number }
  status: 'active' | 'finished' | 'expired'
  status_label: string
  started_at: string
  finished_at: string | null
  duration_seconds: number | null
  score: {
    earned: number
    possible: number
    percent: number
    correct: number
    wrong: number
    pending: number
    unanswered: number
    total_questions: number
    passed: boolean | null
  } | null
  /** Short-lived signed links to the test pages (the same pages students use). */
  take_url: string | null
  result_url: string | null
}

/** `GET /tests/` — the test bank, read-only for a Team Lead. */
export interface TestBankItem {
  id: string
  title: string
  subject_name: string | null
  level_display: string
  status: 'draft' | 'active' | 'archived'
  status_display: string
  time_limit_minutes: number | null
  passing_score: number
  question_count: number | null
  attempt_count: number | null
}
